import getpass
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Self

from sqlalchemy import (
    ColumnElement,
    Executable,
    Update,
    delete,
    select,
    text,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from esmigrate.commons import DEFAULT_NAMESPACE, Direction, Migration, MigVersion
from esmigrate.exceptions import (
    InvalidDBConnectionError,
    LegacySchemaTableError,
    SchemaVersionSqlDbError,
)
from esmigrate.internals.db_engine import check_schema_exists, create_engine, verify_schema_columns
from esmigrate.internals.legacy_layout import Layout, copy_old_rows, detect_layout
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
from esmigrate.models import Base, SchemaHistory, SchemaState


@dataclass(frozen=True)
class ScriptRun:
    """Started run of one script, used to record its result"""

    direction: Direction
    version: MigVersion
    history_id: int


def migration_to_state(
    migration: Migration, namespace: str, installed_rank: int, user: str, now: datetime
) -> SchemaState:
    """Build the state row that starts an up run"""
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
    """Build the history row of a run"""
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


class DBManager:
    """Schema database access for one namespace"""

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
        """Connect, refuse or copy old layouts, create missing tables, and dispose the engine on exit"""
        base_engine = create_engine(db_url, echo)
        engine = base_engine.execution_options(schema_translate_map={None: schema}) if schema else base_engine
        try:
            layout = Layout.CURRENT
            try:
                async with engine.connect() as conn:
                    await conn.run_sync(check_schema_exists, schema)
                    layout = await conn.run_sync(detect_layout, schema)
            except (SQLAlchemyError, OSError, TypeError) as err:
                raise InvalidDBConnectionError(
                    f"Cannot connect to the schema database: {type(err).__name__}: {err}"
                ) from err
            if layout is not Layout.CURRENT and not upgrade:
                raise LegacySchemaTableError(f"Schema tables use the {layout} layout, run `esmigrate init` to upgrade")
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                    await conn.run_sync(verify_schema_columns, schema)
            except SQLAlchemyError as err:
                raise InvalidDBConnectionError(
                    f"Cannot create the schema tables: {err}, "
                    "use `esmigrate init --print-sql` if this account cannot create tables"
                ) from err
            if layout is not Layout.CURRENT:
                try:
                    async with engine.begin() as conn:
                        await conn.run_sync(copy_old_rows, layout, schema)
                except SQLAlchemyError as err:
                    raise SchemaVersionSqlDbError(f"Cannot copy existing schema versions: {err}") from err
            yield cls(engine, namespace, upgraded_from=layout, schema=schema)
        finally:
            await base_engine.dispose()

    @asynccontextmanager
    async def lock(self, timeout: float = 0) -> AsyncGenerator[None, None]:
        """Hold the migration lock of the namespace for the duration of the block"""
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
        """Commit the start of a run before its first request"""
        user = getpass.getuser()
        now = datetime.now(UTC)
        version = migration.version
        history = migration_to_history(direction, migration, self.namespace, user, now)
        async with self._sessionmaker() as session:
            try:
                latest = await self._find_latest_schema(session, self.namespace)
                if latest and not latest.success:
                    raise SchemaVersionSqlDbError(
                        f"Version {latest.version} failed or was interrupted, see `esmigrate status`"
                    )
                if direction is Direction.UP:
                    if await session.get(SchemaState, (self.namespace, version.base, version.rank)):
                        raise SchemaVersionSqlDbError(f"Version {version} is already applied")
                    installed_rank = (latest.installed_rank or 0) + 1 if latest else 1
                    state = migration_to_state(
                        migration=migration, namespace=self.namespace, installed_rank=installed_rank, user=user, now=now
                    )
                    session.add(state)
                elif latest is None or latest.version != version:
                    raise SchemaVersionSqlDbError(f"Version {version} is not the latest applied version")
                else:
                    latest.success = None
                session.add(history)
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(f"Cannot write to the schema database: {err}") from err
        return ScriptRun(direction, version, history.id)

    async def finish_run(self, run: ScriptRun, success: bool, duration: int, query_results: str) -> None:
        """Commit the result of a run"""
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
        """Revert the start of a run that never reached Elasticsearch, keeping a failed history row"""
        state = self._state_filter(run.version)
        change: Executable
        if run.direction is Direction.UP:
            change = delete(SchemaState).where(*state)
        else:
            change = update(SchemaState).where(*state).values(success=True)
        await self._commit_run(change, self._history_result(run, False, duration, query_results))

    async def _lock_identity(self, conn: AsyncConnection) -> str:
        """Identify the lock by database, schema and namespace"""
        database = self._engine.url.database or ""
        schema = self.schema
        if schema is None and conn.dialect.name == "postgresql":
            schema = str((await conn.execute(text("SELECT current_schema()"))).scalar())
        return f"{database}:{schema or database}:{self.namespace}"

    async def force_unlock(self) -> bool | None:
        """Remove a stuck SQLite lock, or return None where the database releases locks itself"""
        if self._engine.dialect.name != "sqlite":
            return None
        return await force_release_sqlite_lock(self._engine, self.namespace)

    async def find_schema_by_version(self, version: MigVersion) -> SchemaState | None:
        """Return the state row of a version, if recorded"""
        async with self._sessionmaker() as session:
            return await session.get(SchemaState, (self.namespace, version.base, version.rank))

    async def find_latest_schema(self) -> SchemaState | None:
        """Return the most recently installed state row, if any"""
        async with self._sessionmaker() as session:
            return await self._find_latest_schema(session, self.namespace)

    async def find_all_schema(self) -> Sequence[SchemaState]:
        """Return every state row in installation order"""
        async with self._sessionmaker() as session:
            query = select(SchemaState).where(SchemaState.namespace == self.namespace)
            return (await session.scalars(query.order_by(SchemaState.installed_rank))).all()

    async def find_applied_versions(self) -> set[MigVersion]:
        """Return the versions that have a state row"""
        query = select(SchemaState.version_base, SchemaState.version_rank)
        async with self._sessionmaker() as session:
            rows = await session.execute(query.where(SchemaState.namespace == self.namespace))
            return {MigVersion(base, rank) for base, rank in rows}

    async def delete_all_failed_schema(self) -> None:
        """Delete the failed state rows"""
        await self._delete(SchemaState.success.is_(False))

    async def delete_all_schema(self, cutoff_rank: int = 0) -> None:
        """Delete the state rows from the given installed rank on"""
        await self._delete(SchemaState.installed_rank >= cutoff_rank)

    async def find_history(self) -> Sequence[SchemaHistory]:
        """Return every history row in event order"""
        async with self._sessionmaker() as session:
            query = select(SchemaHistory).where(SchemaHistory.namespace == self.namespace)
            return (await session.scalars(query.order_by(SchemaHistory.id))).all()

    async def _delete(self, condition: ColumnElement[bool]) -> None:
        """Delete the state rows that match a condition"""
        async with self._sessionmaker() as session:
            try:
                await session.execute(delete(SchemaState).where(SchemaState.namespace == self.namespace, condition))
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(f"Cannot write to the schema database: {err}") from err

    async def _commit_run(self, *statements: Executable) -> None:
        """Execute the statements of a run in one transaction"""
        async with self._sessionmaker() as session:
            try:
                for statement in statements:
                    await session.execute(statement)
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(f"Cannot write to the schema database: {err}") from err

    def _state_filter(self, version: MigVersion) -> tuple[ColumnElement[bool], ...]:
        """Return the conditions that select the state row of a version"""
        return (
            SchemaState.namespace == self.namespace,
            SchemaState.version_base == version.base,
            SchemaState.version_rank == version.rank,
        )

    @staticmethod
    async def _find_latest_schema(session: AsyncSession, namespace: str) -> SchemaState | None:
        """Return the most recently installed state row of a namespace"""
        query = select(SchemaState).where(SchemaState.namespace == namespace)
        query = query.order_by(SchemaState.installed_rank.desc())
        return (await session.scalars(query)).first()

    @staticmethod
    def _history_result(run: ScriptRun, success: bool, duration: int, query_results: str) -> Update:
        """Return the update that stores the result of a run in its history row"""
        return (
            update(SchemaHistory)
            .where(SchemaHistory.id == run.history_id)
            .values(success=success, execution_time=duration, query_results=query_results)
        )
