import getpass
import re
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from sqlalchemy import (
    ColumnElement,
    Connection,
    Executable,
    Update,
    delete,
    insert,
    inspect,
    literal,
    select,
    table,
    text,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from esmigrate.commons import DEFAULT_NAMESPACE, Direction, Migration, MigVersion, Operation, old_timestamp_to_utc
from esmigrate.exceptions import (
    InvalidDBConnectionError,
    LegacySchemaTableError,
    SchemaVersionSqlDbError,
    error_list,
)
from esmigrate.internals.db_engine import check_schema_exists, create_engine, verify_schema_columns
from esmigrate.internals.migration_lock import (
    acquire_mysql_lock,
    acquire_postgresql_lock,
    acquire_sqlite_lock,
    force_release_sqlite_lock,
    mysql_lock_name,
    postgresql_lock_key,
    release_mysql_lock,
    release_postgresql_lock,
    release_sqlite_lock,
)
from esmigrate.models import HISTORY_TABLE, STATE_TABLE, Base, SchemaHistory, SchemaState

LEGACY_TABLE = "esm_schema_version"


class Layout(StrEnum):
    CURRENT = "CURRENT"
    V1 = "V1"
    V2 = "V2"


@dataclass(frozen=True)
class ScriptRun:
    direction: Direction
    version: MigVersion
    history_id: int


def qualified_name(conn: Connection, table: str, schema: str | None) -> str:
    preparer = conn.dialect.identifier_preparer
    name = preparer.quote(table)
    return f"{preparer.quote_schema(schema)}.{name}" if schema else name


def table_has_rows(conn: Connection, table_name: str, schema: str | None = None) -> bool:
    if not inspect(conn).has_table(table_name, schema=schema):
        return False
    stmt = select(literal(1)).select_from(table(table_name, schema=schema)).limit(1)
    return conn.scalar(stmt) is not None


def detect_layout(conn: Connection, schema: str | None = None) -> Layout:
    if table_has_rows(conn, HISTORY_TABLE.name, schema=schema) or not table_has_rows(conn, LEGACY_TABLE, schema):
        return Layout.CURRENT
    columns = {col["name"] for col in inspect(conn).get_columns(LEGACY_TABLE, schema=schema)}
    return Layout.V2 if "namespace" in columns else Layout.V1


def old_row_to_state(row: Mapping[Any, Any], namespace: str, version: MigVersion, layout: Layout) -> dict[str, Any]:
    script = row["script"]
    if script and layout is Layout.V1:
        script = re.split(r"[\\/]", script)[-1]
    elapsed = row["execution_time"]
    success = row["success"]
    return {
        "namespace": namespace,
        "version_base": version.base,
        "version_rank": version.rank,
        "installed_rank": row["installed_rank"],
        "description": row["description"],
        "type": row["type"],
        "script": script,
        "checksum": row["checksum"],
        "installed_by": row["installed_by"],
        "installed_on": old_timestamp_to_utc(row["installed_on"], layout is Layout.V2),
        "execution_time": None if elapsed is None else elapsed * 1000,
        "success": None if success is None else bool(success),
        "query_results": row["query_results"],
    }


def state_to_history(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "namespace": state["namespace"],
        "version_base": state["version_base"],
        "version_rank": state["version_rank"],
        "operation": Operation.UP.value,
        "description": state["description"],
        "script": state["script"],
        "checksum": state["checksum"],
        "executed_by": state["installed_by"],
        "executed_on": state["installed_on"],
        "execution_time": state["execution_time"],
        "success": state["success"],
        "query_results": state["query_results"],
    }


def migration_to_state(
    migration: Migration, namespace: str, installed_rank: int, user: str, now: datetime
) -> SchemaState:
    up = migration.up
    return SchemaState(
        namespace=namespace,
        version_base=migration.version.base,
        version_rank=migration.version.rank,
        installed_rank=installed_rank,
        description=migration.description,
        type="NOSQL",
        script=up.path if up else None,
        checksum=up.checksum if up else None,
        installed_by=user,
        installed_on=now,
    )


def migration_to_history(
    direction: Direction, migration: Migration, namespace: str, user: str, now: datetime
) -> SchemaHistory:
    script = migration.script_for(direction)
    return SchemaHistory(
        namespace=namespace,
        version_base=migration.version.base,
        version_rank=migration.version.rank,
        operation=direction.value,
        description=migration.description,
        script=script.path if script else None,
        checksum=script.checksum if script else None,
        executed_by=user,
        executed_on=now,
    )


def copy_old_rows(conn: Connection, layout: Layout, schema: str | None = None) -> None:
    source = qualified_name(conn, LEGACY_TABLE, schema)
    rows = conn.execute(text(f"SELECT * FROM {source}")).mappings().all()

    seen: dict[tuple[str, MigVersion], str] = {}
    states: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in sorted(rows, key=lambda item: item["version"]):
        namespace = row["namespace"] if layout is Layout.V2 else DEFAULT_NAMESPACE
        try:
            version = MigVersion.parse(row["version"])
        except ValueError as err:
            errors.append(f"{namespace}: {err}")
            continue
        earlier = seen.setdefault((namespace, version), row["version"])
        if earlier != row["version"]:
            errors.append(f"{namespace}: {earlier} and {row['version']} are the same version")
            continue
        states.append(old_row_to_state(row, namespace, version, layout))
    if errors:
        raise SchemaVersionSqlDbError(error_list("Cannot copy existing schema versions:", errors))

    states.sort(key=lambda state: (state["namespace"], state["installed_rank"] or 0))
    conn.execute(insert(STATE_TABLE), states)
    conn.execute(insert(HISTORY_TABLE), [state_to_history(state) for state in states])


class DBManager:
    def __init__(
        self,
        engine: AsyncEngine,
        namespace: str = DEFAULT_NAMESPACE,
        upgraded_from: Layout = Layout.CURRENT,
        schema: str | None = None,
    ) -> None:
        self._engine = engine
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        self.namespace = namespace
        self.schema = schema
        self.upgraded_from = upgraded_from

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
            layout = Layout.CURRENT
            try:
                async with engine.connect() as conn:
                    await conn.run_sync(check_schema_exists, schema)
                    layout = await conn.run_sync(detect_layout, schema)
            except (SQLAlchemyError, OSError, TypeError) as err:
                raise InvalidDBConnectionError(f"{type(err).__name__}: {err}") from err
            if layout is not Layout.CURRENT and not upgrade:
                raise LegacySchemaTableError(f"Schema tables use the {layout} layout, run `esmigrate init` to upgrade")
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                    await conn.run_sync(verify_schema_columns, schema)
            except SQLAlchemyError as err:
                raise InvalidDBConnectionError(
                    f"{err}, use `esmigrate init --print-sql` if this account cannot create tables"
                ) from err
            if layout is not Layout.CURRENT:
                try:
                    async with engine.begin() as conn:
                        await conn.run_sync(copy_old_rows, layout, schema)
                except SQLAlchemyError as err:
                    raise SchemaVersionSqlDbError(f"Copying existing schema versions failed: {err}") from err
            yield cls(engine, namespace, upgraded_from=layout, schema=schema)
        finally:
            await base_engine.dispose()

    @asynccontextmanager
    async def lock(self, timeout: float = 0) -> AsyncGenerator[None, None]:
        dialect = self._engine.dialect.name
        if dialect == "sqlite":
            await acquire_sqlite_lock(self._engine, self.namespace, timeout)
            try:
                yield
            finally:
                await release_sqlite_lock(self._engine, self.namespace)
            return
        if dialect not in ("postgresql", "mysql"):
            raise InvalidDBConnectionError(f"Migration locks are not supported for {dialect}")
        async with self._engine.connect() as raw_conn:
            conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
            identity = await self._lock_identity(conn)
            if dialect == "postgresql":
                key = postgresql_lock_key(identity)
                await acquire_postgresql_lock(conn, key, timeout)
                try:
                    yield
                finally:
                    await release_postgresql_lock(conn, key)
            else:
                name = mysql_lock_name(identity)
                await acquire_mysql_lock(conn, name, timeout)
                try:
                    yield
                finally:
                    await release_mysql_lock(conn, name)

    async def start_run(self, direction: Direction, migration: Migration) -> ScriptRun:
        user = getpass.getuser()
        now = datetime.now(UTC)
        version = migration.version
        history = migration_to_history(direction, migration, self.namespace, user, now)
        async with self._sessionmaker() as session:
            try:
                latest = await self._find_latest_schema(session, self.namespace)
                if latest and not latest.success:
                    raise SchemaVersionSqlDbError(f"Failed previous version: {latest.version}")
                if direction is Direction.UP:
                    if await session.get(SchemaState, (self.namespace, version.base, version.rank)):
                        raise SchemaVersionSqlDbError(f"Version already installed: {version}")
                    installed_rank = (latest.installed_rank or 0) + 1 if latest else 1
                    state = migration_to_state(
                        migration=migration, namespace=self.namespace, installed_rank=installed_rank, user=user, now=now
                    )
                    session.add(state)
                elif latest is None or latest.version != version:
                    raise SchemaVersionSqlDbError(f"Version is not the latest applied: {version}")
                else:
                    latest.success = None
                session.add(history)
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(str(err)) from err
        return ScriptRun(direction, version, history.id)

    async def finish_run(self, run: ScriptRun, success: bool, duration: int, query_results: str) -> None:
        state = self._state_filter(run.version)
        change: Executable
        if run.direction is Direction.UP:
            change = (
                update(SchemaState)
                .where(*state)
                .values(success=success, execution_time=duration, query_results=query_results)
            )
        elif success:
            change = delete(SchemaState).where(*state)
        else:
            change = update(SchemaState).where(*state).values(success=False)
        await self._commit_run(change, self._history_result(run, success, duration, query_results))

    async def undo_run(self, run: ScriptRun, duration: int, query_results: str) -> None:
        state = self._state_filter(run.version)
        change: Executable
        if run.direction is Direction.UP:
            change = delete(SchemaState).where(*state)
        else:
            change = update(SchemaState).where(*state).values(success=True)
        await self._commit_run(change, self._history_result(run, False, duration, query_results))

    async def _lock_identity(self, conn: AsyncConnection) -> str:
        database = self._engine.url.database or ""
        schema = self.schema
        if schema is None and conn.dialect.name == "postgresql":
            schema = str((await conn.execute(text("SELECT current_schema()"))).scalar())
        return f"{database}:{schema or database}:{self.namespace}"

    async def force_unlock(self) -> bool | None:
        if self._engine.dialect.name != "sqlite":
            return None
        return await force_release_sqlite_lock(self._engine, self.namespace)

    async def find_schema_by_version(self, version: MigVersion) -> SchemaState | None:
        async with self._sessionmaker() as session:
            return await session.get(SchemaState, (self.namespace, version.base, version.rank))

    async def find_latest_schema(self) -> SchemaState | None:
        async with self._sessionmaker() as session:
            return await self._find_latest_schema(session, self.namespace)

    async def find_all_schema(self) -> Sequence[SchemaState]:
        async with self._sessionmaker() as session:
            query = select(SchemaState).where(SchemaState.namespace == self.namespace)
            return (await session.scalars(query.order_by(SchemaState.installed_rank))).all()

    async def find_applied_versions(self) -> set[MigVersion]:
        query = select(SchemaState.version_base, SchemaState.version_rank)
        async with self._sessionmaker() as session:
            rows = await session.execute(query.where(SchemaState.namespace == self.namespace))
            return {MigVersion(base, rank) for base, rank in rows}

    async def delete_all_failed_schema(self) -> None:
        await self._delete(SchemaState.success.is_(False))

    async def delete_all_schema(self, cutoff_rank: int = 0) -> None:
        await self._delete(SchemaState.installed_rank >= cutoff_rank)

    async def find_history(self) -> Sequence[SchemaHistory]:
        async with self._sessionmaker() as session:
            query = select(SchemaHistory).where(SchemaHistory.namespace == self.namespace)
            return (await session.scalars(query.order_by(SchemaHistory.id))).all()

    async def _delete(self, condition: ColumnElement[bool]) -> None:
        async with self._sessionmaker() as session:
            try:
                await session.execute(delete(SchemaState).where(SchemaState.namespace == self.namespace, condition))
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(str(err)) from err

    async def _commit_run(self, *statements: Executable) -> None:
        async with self._sessionmaker() as session:
            try:
                for statement in statements:
                    await session.execute(statement)
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(str(err)) from err

    def _state_filter(self, version: MigVersion) -> tuple[ColumnElement[bool], ...]:
        return (
            SchemaState.namespace == self.namespace,
            SchemaState.version_base == version.base,
            SchemaState.version_rank == version.rank,
        )

    @staticmethod
    async def _find_latest_schema(session: AsyncSession, namespace: str) -> SchemaState | None:
        query = select(SchemaState).where(SchemaState.namespace == namespace)
        query = query.order_by(SchemaState.installed_rank.desc())
        return (await session.scalars(query)).first()

    @staticmethod
    def _history_result(run: ScriptRun, success: bool, duration: int, query_results: str) -> Update:
        return (
            update(SchemaHistory)
            .where(SchemaHistory.id == run.history_id)
            .values(success=success, execution_time=duration, query_results=query_results)
        )
