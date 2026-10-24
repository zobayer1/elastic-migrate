import re
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Self

from sqlalchemy import URL, ColumnElement, Connection, Table, delete, insert, inspect, make_url, select, text
from sqlalchemy.exc import ArgumentError, InvalidRequestError, NoSuchModuleError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from esmigrate.commons import DEFAULT_NAMESPACE
from esmigrate.exceptions import InvalidDBConnectionError, LegacySchemaTableError, SchemaVersionSqlDbError
from esmigrate.models import SchemaVersion
from esmigrate.models.base import Base

ASYNC_DRIVERS = {
    "sqlite": "sqlite+aiosqlite",
    "postgres": "postgresql+asyncpg",
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+asyncmy",
    "mariadb": "mysql+asyncmy",
}

DRIVER_EXTRAS = {
    "asyncpg": "postgres",
    "asyncmy": "mysql",
}

LEGACY_BACKUP_TABLE = "esm_schema_version_v1_backup"
SCHEMA_TABLE: Table = Base.metadata.tables[SchemaVersion.__tablename__]


def to_async_url(db_url: str) -> URL:
    try:
        url = make_url(db_url)
    except ArgumentError as err:
        raise InvalidDBConnectionError(str(err)) from err
    if "+" in url.drivername:
        return url
    if url.drivername not in ASYNC_DRIVERS:
        raise InvalidDBConnectionError(f"Unsupported database: {url.drivername}")
    return url.set(drivername=ASYNC_DRIVERS[url.drivername])


def create_engine(db_url: str, echo: bool = False) -> AsyncEngine:
    url = to_async_url(db_url)
    try:
        return create_async_engine(url, echo=echo)
    except ModuleNotFoundError as err:
        extra = DRIVER_EXTRAS.get(err.name or "")
        hint = f", install elastic-migrate[{extra}]" if extra else ""
        raise InvalidDBConnectionError(f"Database driver not installed: {err.name}{hint}") from err
    except (InvalidRequestError, NoSuchModuleError) as err:
        raise InvalidDBConnectionError(f"Unsupported database driver: {url.drivername}, {err}") from err


def qualified_name(conn: Connection, table: str, schema: str | None) -> str:
    preparer = conn.dialect.identifier_preparer
    name = preparer.quote(table)
    return f"{preparer.quote_schema(schema)}.{name}" if schema else name


def check_schema_exists(conn: Connection, schema: str | None) -> None:
    if schema is not None and schema not in inspect(conn).get_schema_names():
        raise InvalidDBConnectionError(f"Database schema {schema} does not exist")


def is_legacy_table(conn: Connection, schema: str | None = None) -> bool:
    inspector = inspect(conn)
    if not inspector.has_table(SCHEMA_TABLE.name, schema=schema):
        return False
    columns = inspector.get_columns(SCHEMA_TABLE.name, schema=schema)
    return "namespace" not in {column["name"] for column in columns}


def upgrade_legacy_table(conn: Connection, schema: str | None = None) -> None:
    if inspect(conn).has_table(LEGACY_BACKUP_TABLE, schema=schema):
        raise SchemaVersionSqlDbError(f"Backup table {LEGACY_BACKUP_TABLE} already exists, remove it before upgrading")
    table = SCHEMA_TABLE
    backup = qualified_name(conn, LEGACY_BACKUP_TABLE, schema)
    current = qualified_name(conn, table.name, schema)
    conn.execute(text(f"CREATE TABLE {backup} AS SELECT * FROM {current}"))
    rows = conn.execute(text(f"SELECT * FROM {backup}")).mappings().all()
    conn.execute(text(f"DROP TABLE {current}"))
    table.create(conn)
    if rows:
        conn.execute(insert(table), [upgrade_legacy_row(row) for row in rows])


def upgrade_legacy_row(row: Mapping[Any, Any]) -> dict[str, Any]:
    values = {column.name: row[column.name] for column in SCHEMA_TABLE.columns if column.name in row}
    values["namespace"] = DEFAULT_NAMESPACE
    if values.get("script"):
        values["script"] = re.split(r"[\\/]", values["script"])[-1]
    if values.get("success") is not None:
        values["success"] = bool(values["success"])
    installed_on = values.get("installed_on")
    if isinstance(installed_on, str):
        installed_on = datetime.fromisoformat(installed_on)
    if installed_on is not None:
        values["installed_on"] = installed_on.astimezone(UTC)
    return values


class DBManager:
    def __init__(
        self,
        engine: AsyncEngine,
        namespace: str = DEFAULT_NAMESPACE,
        upgraded: bool = False,
        schema: str | None = None,
    ) -> None:
        self._engine = engine
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        self.namespace = namespace
        self.schema = schema
        self.upgraded_legacy_table = upgraded

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        db_url: str,
        namespace: str = DEFAULT_NAMESPACE,
        upgrade: bool = False,
        echo: bool = False,
        schema: str | None = None,
    ) -> AsyncGenerator[Self, None]:
        base_engine = create_engine(db_url, echo)
        engine = base_engine.execution_options(schema_translate_map={None: schema}) if schema else base_engine
        try:
            try:
                async with engine.connect() as conn:
                    await conn.run_sync(check_schema_exists, schema)
                    legacy = await conn.run_sync(is_legacy_table, schema)
            except (SQLAlchemyError, OSError, TypeError) as err:
                raise InvalidDBConnectionError(f"{type(err).__name__}: {err}") from err
            if legacy and not upgrade:
                raise LegacySchemaTableError("Schema version table uses the v1 layout, run `esmigrate init` to upgrade")
            if legacy:
                try:
                    async with engine.begin() as conn:
                        await conn.run_sync(upgrade_legacy_table, schema)
                except SQLAlchemyError as err:
                    raise SchemaVersionSqlDbError(f"Legacy table upgrade failed: {err}") from err
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            except SQLAlchemyError as err:
                raise InvalidDBConnectionError(str(err)) from err
            yield cls(engine, namespace, upgraded=legacy, schema=schema)
        finally:
            await base_engine.dispose()

    async def schema_version_exists(self) -> bool:
        async with self._engine.connect() as conn:
            tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names(schema=self.schema))
        return SCHEMA_TABLE.name in tables

    async def insert_new_schema(self, scmver: SchemaVersion) -> None:
        async with self._sessionmaker() as session:
            try:
                scmver.namespace = self.namespace
                if await session.get(SchemaVersion, (self.namespace, scmver.version)):
                    raise SchemaVersionSqlDbError(f"Version already installed: {scmver.version}")
                scmver_latest = await self._find_latest_schema(session, self.namespace)
                if scmver_latest and not scmver_latest.success:
                    raise SchemaVersionSqlDbError(f"Failed previous version: {scmver_latest.version}")
                scmver.installed_rank = (scmver_latest.installed_rank or 0) + 1 if scmver_latest else 1
                session.add(scmver)
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(str(err)) from err

    async def find_schema_by_version(self, version: str) -> SchemaVersion | None:
        async with self._sessionmaker() as session:
            return await session.get(SchemaVersion, (self.namespace, version))

    async def find_latest_schema(self) -> SchemaVersion | None:
        async with self._sessionmaker() as session:
            return await self._find_latest_schema(session, self.namespace)

    async def find_all_schema(self) -> Sequence[SchemaVersion]:
        async with self._sessionmaker() as session:
            query = select(SchemaVersion).where(SchemaVersion.namespace == self.namespace)
            return (await session.scalars(query.order_by(SchemaVersion.installed_rank))).all()

    async def delete_all_failed_schema(self) -> None:
        await self._delete(SchemaVersion.success.is_(False))

    async def delete_all_schema(self, cutoff_rank: int = 0) -> None:
        await self._delete(SchemaVersion.installed_rank >= cutoff_rank)

    async def _delete(self, condition: ColumnElement[bool]) -> None:
        async with self._sessionmaker() as session:
            try:
                await session.execute(delete(SchemaVersion).where(SchemaVersion.namespace == self.namespace, condition))
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(str(err)) from err

    @staticmethod
    async def _find_latest_schema(session: AsyncSession, namespace: str) -> SchemaVersion | None:
        query = select(SchemaVersion).where(SchemaVersion.namespace == namespace)
        query = query.order_by(SchemaVersion.installed_rank.desc())
        return (await session.scalars(query)).first()
