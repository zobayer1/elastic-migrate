import asyncio
import os
import socket
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import insert, select

from esmigrate.exceptions import InvalidDBConnectionError, MigrationLockedError
from esmigrate.internals import DBManager
from esmigrate.internals.migration_lock import (
    LOCK_TABLE,
    acquire_mysql_lock,
    acquire_postgresql_lock,
    mysql_lock_name,
    poll,
    postgresql_lock_key,
    process_exists,
    release_mysql_lock,
    release_postgresql_lock,
)


def scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def fake_conn(*values):
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=[scalar_result(value) for value in values])
    return conn


def dead_pid():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


@pytest.fixture
def db_url(tmp_path):
    """pytest fixture for a file-backed SQLite URL in a temporary directory"""
    return f"sqlite:///{tmp_path / 'esmigrate.db'}"


async def lock_rows(db):
    async with db._engine.connect() as conn:
        return (await conn.execute(select(LOCK_TABLE))).mappings().all()


async def insert_lock_row(db, host, pid, namespace="default"):
    async with db.lock(timeout=0):
        pass
    async with db._engine.begin() as conn:
        await conn.execute(
            insert(LOCK_TABLE).values(
                namespace=namespace, owner_host=host, owner_pid=pid, acquired_at=datetime.now(UTC)
            )
        )


def test_postgresql_lock_key_is_stable_signed_64_bit():
    """Test fails if the advisory lock key is unstable, out of bigint range or shared between identities"""
    key = postgresql_lock_key("db:schema:default")
    assert key == postgresql_lock_key("db:schema:default")
    assert -(2**63) <= key < 2**63
    assert key != postgresql_lock_key("db:other:default")


def test_mysql_lock_name_fits_limit():
    """Test fails if the MySQL lock name exceeds 64 characters or is shared between identities"""
    name = mysql_lock_name("db:db:" + "n" * 64)
    assert name.startswith("esmigrate:")
    assert len(name) <= 64
    assert name != mysql_lock_name("db:db:other")


def test_process_exists_for_running_and_finished_processes():
    """Test fails if the current process is not alive or a finished process is reported alive"""
    assert process_exists(os.getpid())
    assert not process_exists(dead_pid())


def test_process_exists_treats_permission_errors_as_alive(mocker):
    """Test fails if a process owned by another user is considered dead"""
    mocker.patch("esmigrate.internals.migration_lock.os.kill", side_effect=PermissionError)
    assert process_exists(1)


def test_process_exists_never_signals_on_windows(mocker, monkeypatch):
    """Test fails if the Windows path calls os.kill, which would send CTRL_C_EVENT instead of probing"""
    kill = mocker.patch("esmigrate.internals.migration_lock.os.kill")
    monkeypatch.setattr("esmigrate.internals.migration_lock.os.name", "nt")
    assert process_exists(12345)
    kill.assert_not_called()


async def test_poll_retries_until_success_or_timeout(mocker):
    """Test fails if poll does not retry within the timeout or keeps going after it"""
    mocker.patch("esmigrate.internals.migration_lock.LOCK_POLL_INTERVAL", 0.01)
    attempts = AsyncMock(side_effect=[False, False, True])
    assert await poll(attempts, timeout=5)
    assert attempts.await_count == 3
    never = AsyncMock(return_value=False)
    assert not await poll(never, timeout=0)
    assert never.await_count == 1


async def test_postgresql_lock_acquires_and_releases():
    """Test fails if the PostgreSQL advisory lock is not taken and released with the key"""
    conn = fake_conn(True, None)
    await acquire_postgresql_lock(conn, 42, timeout=0)
    await release_postgresql_lock(conn, 42)
    statements = [str(call.args[0]) for call in conn.execute.await_args_list]
    assert statements == ["SELECT pg_try_advisory_lock(:key)", "SELECT pg_advisory_unlock(:key)"]


@pytest.mark.parametrize(("holder", "message"), [(4242, "by PostgreSQL backend pid 4242"), (None, "held$")])
async def test_postgresql_lock_reports_holder(holder, message):
    """Test fails if a busy advisory lock is not reported with the holding backend when known"""
    conn = fake_conn(False, holder)
    with pytest.raises(MigrationLockedError, match=message):
        await acquire_postgresql_lock(conn, -(2**40) - 7, timeout=0)
    assert conn.execute.await_args_list[1].args[1] == {"classid": 0xFFFFFEFF, "objid": 0xFFFFFFF9}


async def test_mysql_lock_acquires_and_releases():
    """Test fails if GET_LOCK and RELEASE_LOCK are not called with the lock name and rounded timeout"""
    conn = fake_conn(1, 1)
    await acquire_mysql_lock(conn, "esmigrate:x", timeout=1.2)
    await release_mysql_lock(conn, "esmigrate:x")
    assert conn.execute.await_args_list[0].args[1] == {"name": "esmigrate:x", "timeout": 2}
    assert str(conn.execute.await_args_list[1].args[0]) == "SELECT RELEASE_LOCK(:name)"


@pytest.mark.parametrize(("acquired", "holder", "message"), [(0, 17, "by MySQL connection 17"), (None, None, "held$")])
async def test_mysql_lock_reports_holder(acquired, holder, message):
    """Test fails if a busy or failed GET_LOCK is not reported with the holding connection when known"""
    with pytest.raises(MigrationLockedError, match=message):
        await acquire_mysql_lock(fake_conn(acquired, holder), "esmigrate:x", timeout=0)


async def test_sqlite_lock_is_held_and_released(db_url):
    """Test fails if the SQLite lock row is not present while held and removed afterwards"""
    async with DBManager.connect(db_url) as db:
        async with db.lock():
            rows = await lock_rows(db)
            assert [(row["namespace"], row["owner_host"], row["owner_pid"]) for row in rows] == [
                ("default", socket.gethostname(), os.getpid())
            ]
        assert await lock_rows(db) == []


async def test_sqlite_lock_fails_immediately_when_held(db_url):
    """Test fails if a second holder is not rejected with the holder's host, pid and time"""
    async with DBManager.connect(db_url) as first, DBManager.connect(db_url) as second, first.lock():
        with pytest.raises(MigrationLockedError, match=rf"held by {socket.gethostname()} pid {os.getpid()} since 20"):
            async with second.lock(timeout=0):
                pass


async def test_sqlite_lock_is_per_namespace(db_url):
    """Test fails if namespaces block each other"""
    async with (
        DBManager.connect(db_url, namespace="alpha") as alpha,
        DBManager.connect(db_url, namespace="beta") as beta,
        alpha.lock(),
        beta.lock(timeout=0),
    ):
        assert len(await lock_rows(alpha)) == 2


async def test_sqlite_lock_waits_for_release(db_url, mocker):
    """Test fails if a waiter does not get the lock once the holder releases it within the timeout"""
    mocker.patch("esmigrate.internals.migration_lock.LOCK_POLL_INTERVAL", 0.05)
    async with DBManager.connect(db_url) as first, DBManager.connect(db_url) as second:
        released = asyncio.Event()

        async def hold():
            async with first.lock():
                await asyncio.sleep(0.2)
            released.set()

        holder = asyncio.create_task(hold())
        await asyncio.sleep(0.05)
        async with second.lock(timeout=5):
            assert released.is_set()
        await holder


async def test_sqlite_lock_takes_over_stale_lock_on_same_host(db_url):
    """Test fails if a lock left by a dead process on this host is not taken over"""
    async with DBManager.connect(db_url) as db:
        await insert_lock_row(db, socket.gethostname(), dead_pid())
        async with db.lock(timeout=0):
            assert [row["owner_pid"] for row in await lock_rows(db)] == [os.getpid()]


@pytest.mark.parametrize("owner", ["other-host", "same-host-live"])
async def test_sqlite_lock_respects_live_or_remote_holders(db_url, owner):
    """Test fails if a lock held by another host or a live local process is taken over"""
    host, pid = ("other-host", dead_pid()) if owner == "other-host" else (socket.gethostname(), 1)
    async with DBManager.connect(db_url) as db:
        await insert_lock_row(db, host, pid)
        with pytest.raises(MigrationLockedError, match=f"held by {host} pid {pid}"):
            async with db.lock(timeout=0):
                pass


async def test_sqlite_lock_reports_unknown_holder_when_row_vanishes(db_url, mocker):
    """Test fails if a lock row disappearing between attempts is not reported cleanly"""
    mocker.patch("esmigrate.internals.migration_lock.try_insert_sqlite_lock", AsyncMock(return_value=False))
    async with DBManager.connect(db_url) as db:
        with pytest.raises(MigrationLockedError, match="held by None pid None since unknown"):
            async with db.lock(timeout=0):
                pass


async def test_sqlite_release_keeps_other_holders_rows(db_url):
    """Test fails if releasing removes a lock row owned by another process"""
    async with DBManager.connect(db_url) as db:
        await insert_lock_row(db, "other-host", 99, namespace="other")
        async with db.lock():
            pass
        assert [row["namespace"] for row in await lock_rows(db)] == ["other"]


async def test_force_unlock_removes_stuck_sqlite_lock(db_url):
    """Test fails if force_unlock does not remove a stuck lock and report whether one existed"""
    async with DBManager.connect(db_url) as db:
        await insert_lock_row(db, "other-host", 99)
        assert await db.force_unlock() is True
        assert await db.force_unlock() is False
        async with db.lock(timeout=0):
            pass


def fake_engine(dialect, conn):
    engine = MagicMock()
    engine.dialect.name = dialect
    engine.url.database = "appdb"
    conn.execution_options = AsyncMock(return_value=conn)
    conn.dialect.name = dialect

    @asynccontextmanager
    async def connect():
        yield conn

    engine.connect = connect
    return engine


@pytest.mark.parametrize(
    ("dialect", "schema", "values", "acquire", "release", "argument"),
    [
        ("postgresql", None, ["public"], "acquire_postgresql_lock", "release_postgresql_lock", "appdb:public:billing"),
        ("postgresql", "tenant", [], "acquire_postgresql_lock", "release_postgresql_lock", "appdb:tenant:billing"),
        ("mysql", None, [], "acquire_mysql_lock", "release_mysql_lock", "appdb:appdb:billing"),
    ],
)
async def test_db_manager_lock_dispatches_by_dialect(mocker, dialect, schema, values, acquire, release, argument):
    """Test fails if server databases do not lock on an autocommit connection with a schema-aware key"""
    conn = fake_conn(*values)
    acquire_mock = mocker.patch(f"esmigrate.internals.db_manager.{acquire}", AsyncMock())
    release_mock = mocker.patch(f"esmigrate.internals.db_manager.{release}", AsyncMock())
    db = DBManager(fake_engine(dialect, conn), namespace="billing", schema=schema)
    async with db.lock(timeout=3):
        acquire_mock.assert_awaited_once()
        release_mock.assert_not_awaited()
    release_mock.assert_awaited_once()
    conn.execution_options.assert_awaited_once_with(isolation_level="AUTOCOMMIT")
    expected = postgresql_lock_key(argument) if dialect == "postgresql" else mysql_lock_name(argument)
    assert acquire_mock.await_args.args[1:] == (expected, 3)


async def test_db_manager_lock_rejects_unsupported_dialect():
    """Test fails if a database without lock support is used without an error"""
    db = DBManager(fake_engine("mssql", fake_conn()))
    with pytest.raises(InvalidDBConnectionError, match="not supported for mssql"):
        async with db.lock():
            pass


async def test_force_unlock_is_not_applicable_to_server_databases():
    """Test fails if force_unlock claims to act on advisory locks"""
    assert await DBManager(fake_engine("postgresql", fake_conn())).force_unlock() is None
