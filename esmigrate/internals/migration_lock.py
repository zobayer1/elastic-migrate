import asyncio
import hashlib
import math
import os
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import Column, Integer, MetaData, String, Table, delete, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from esmigrate.exceptions import MigrationLockedError
from esmigrate.models.types import UTCDateTime

LOCK_POLL_INTERVAL = 0.5
LOCK_METADATA = MetaData()
LOCK_TABLE = Table(
    "esm_schema_lock",
    LOCK_METADATA,
    Column("namespace", String(64), primary_key=True),
    Column("owner_host", String(255), nullable=False),
    Column("owner_pid", Integer, nullable=False),
    Column("acquired_at", UTCDateTime, nullable=False),
)


def lock_digest(identity: str) -> bytes:
    return hashlib.sha256(f"esmigrate:{identity}".encode()).digest()


def postgresql_lock_key(identity: str) -> int:
    return int.from_bytes(lock_digest(identity)[:8], "big", signed=True)


def mysql_lock_name(identity: str) -> str:
    return f"esmigrate:{lock_digest(identity).hex()[:54]}"


def process_exists(pid: int) -> bool:
    if os.name == "nt":
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def poll(attempt: Callable[[], Awaitable[bool]], timeout: float) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if await attempt():
            return True
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(LOCK_POLL_INTERVAL, remaining))


async def acquire_postgresql_lock(conn: AsyncConnection, key: int, timeout: float) -> None:
    async def attempt() -> bool:
        return bool((await conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})).scalar())

    if not await poll(attempt, timeout):
        holder = (
            await conn.execute(
                text(
                    "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND granted "
                    "AND classid = :classid AND objid = :objid"
                ),
                {"classid": (key >> 32) & 0xFFFFFFFF, "objid": key & 0xFFFFFFFF},
            )
        ).scalar()
        detail = f" by PostgreSQL backend pid {holder}" if holder is not None else ""
        raise MigrationLockedError(f"Migration lock is held{detail}")


async def release_postgresql_lock(conn: AsyncConnection, key: int) -> None:
    await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


async def acquire_mysql_lock(conn: AsyncConnection, name: str, timeout: float) -> None:
    acquired = (
        await conn.execute(text("SELECT GET_LOCK(:name, :timeout)"), {"name": name, "timeout": math.ceil(timeout)})
    ).scalar()
    if acquired != 1:
        holder = (await conn.execute(text("SELECT IS_USED_LOCK(:name)"), {"name": name})).scalar()
        detail = f" by MySQL connection {holder}" if holder is not None else ""
        raise MigrationLockedError(f"Migration lock is held{detail}")


async def release_mysql_lock(conn: AsyncConnection, name: str) -> None:
    await conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})


async def try_insert_sqlite_lock(engine: AsyncEngine, namespace: str, host: str, pid: int) -> bool:
    try:
        async with engine.begin() as conn:
            await conn.execute(
                insert(LOCK_TABLE).values(
                    namespace=namespace, owner_host=host, owner_pid=pid, acquired_at=datetime.now(UTC)
                )
            )
    except IntegrityError:
        return False
    return True


async def acquire_sqlite_lock(engine: AsyncEngine, namespace: str, timeout: float) -> None:
    host, pid = socket.gethostname(), os.getpid()
    async with engine.begin() as conn:
        await conn.run_sync(LOCK_METADATA.create_all)
    holder: dict[str, object] = {}

    async def attempt() -> bool:
        if await try_insert_sqlite_lock(engine, namespace, host, pid):
            return True
        async with engine.begin() as conn:
            query = select(LOCK_TABLE).where(LOCK_TABLE.c.namespace == namespace)
            row = (await conn.execute(query)).mappings().first()
            if row is None or row["owner_host"] != host or process_exists(row["owner_pid"]):
                holder.update(row or {})
                return False
            await conn.execute(
                delete(LOCK_TABLE).where(
                    LOCK_TABLE.c.namespace == namespace, LOCK_TABLE.c.owner_pid == row["owner_pid"]
                )
            )
        return await try_insert_sqlite_lock(engine, namespace, host, pid)

    if not await poll(attempt, timeout):
        since = holder.get("acquired_at")
        stamp = since.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(since, datetime) else "unknown"
        raise MigrationLockedError(
            f"Migration lock is held by {holder.get('owner_host')} pid {holder.get('owner_pid')} since {stamp}"
        )


async def release_sqlite_lock(engine: AsyncEngine, namespace: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            delete(LOCK_TABLE).where(
                LOCK_TABLE.c.namespace == namespace,
                LOCK_TABLE.c.owner_host == socket.gethostname(),
                LOCK_TABLE.c.owner_pid == os.getpid(),
            )
        )


async def force_release_sqlite_lock(engine: AsyncEngine, namespace: str) -> bool:
    async with engine.begin() as conn:
        await conn.run_sync(LOCK_METADATA.create_all)
        result = await conn.execute(delete(LOCK_TABLE).where(LOCK_TABLE.c.namespace == namespace))
    return result.rowcount > 0
