from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Self

from sqlalchemy import URL, ColumnElement, delete, inspect, make_url, select
from sqlalchemy.exc import ArgumentError, InvalidRequestError, NoSuchModuleError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from esmigrate.exceptions import InvalidDBConnectionError, SchemaVersionSqlDbError
from esmigrate.models import SchemaVersion
from esmigrate.models.base import Base

ASYNC_DRIVERS = {
    "sqlite": "sqlite+aiosqlite",
    "postgres": "postgresql+asyncpg",
    "postgresql": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
    "mariadb": "mysql+aiomysql",
}

DRIVER_EXTRAS = {
    "asyncpg": "postgres",
    "aiomysql": "mysql",
}


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


class DBManager:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    @asynccontextmanager
    async def connect(cls, db_url: str, echo: bool = False) -> AsyncIterator[Self]:
        engine = create_engine(db_url, echo)
        try:
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            except SQLAlchemyError as err:
                raise InvalidDBConnectionError(str(err)) from err
            yield cls(engine)
        finally:
            await engine.dispose()

    async def schema_version_exists(self) -> bool:
        async with self._engine.connect() as conn:
            tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        return SchemaVersion.__tablename__ in tables

    async def insert_new_schema(self, scmver: SchemaVersion) -> None:
        async with self._sessionmaker() as session:
            try:
                if await session.get(SchemaVersion, scmver.version):
                    raise SchemaVersionSqlDbError(f"Version already installed: {scmver.version}")
                scmver_latest = await self._find_latest_schema(session)
                if scmver_latest and not scmver_latest.success:
                    raise SchemaVersionSqlDbError(f"Failed previous version: {scmver_latest.version}")
                scmver.installed_rank = scmver_latest.installed_rank + 1 if scmver_latest else 1
                session.add(scmver)
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(str(err)) from err

    async def find_schema_by_version(self, version: str) -> SchemaVersion | None:
        async with self._sessionmaker() as session:
            return await session.get(SchemaVersion, version)

    async def find_latest_schema(self) -> SchemaVersion | None:
        async with self._sessionmaker() as session:
            return await self._find_latest_schema(session)

    async def find_all_schema(self) -> Sequence[SchemaVersion]:
        async with self._sessionmaker() as session:
            return (await session.scalars(select(SchemaVersion).order_by(SchemaVersion.installed_rank))).all()

    async def delete_all_failed_schema(self) -> None:
        await self._delete(SchemaVersion.success.is_(False))

    async def delete_all_schema(self, cutoff_rank: int = 0) -> None:
        await self._delete(SchemaVersion.installed_rank >= cutoff_rank)

    async def _delete(self, condition: ColumnElement[bool]) -> None:
        async with self._sessionmaker() as session:
            try:
                await session.execute(delete(SchemaVersion).where(condition))
                await session.commit()
            except SQLAlchemyError as err:
                await session.rollback()
                raise SchemaVersionSqlDbError(str(err)) from err

    @staticmethod
    async def _find_latest_schema(session: AsyncSession) -> SchemaVersion | None:
        query = select(SchemaVersion).order_by(SchemaVersion.installed_rank.desc())
        return (await session.scalars(query)).first()
