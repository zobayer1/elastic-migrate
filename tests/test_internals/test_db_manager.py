import sqlite3
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from esmigrate.exceptions import (
    InvalidDBConnectionError,
    LegacySchemaTableError,
    SchemaVersionSqlDbError,
)
from esmigrate.internals import DBManager
from esmigrate.internals.db_manager import LEGACY_BACKUP_TABLE, to_async_url, upgrade_legacy_row
from esmigrate.models import SchemaVersion

LEGACY_TABLE_DDL = """
CREATE TABLE esm_schema_version (
    version VARCHAR NOT NULL PRIMARY KEY,
    version_base INTEGER,
    version_rank INTEGER,
    installed_rank INTEGER UNIQUE,
    description VARCHAR,
    type VARCHAR,
    script VARCHAR,
    checksum BLOB,
    installed_by VARCHAR,
    installed_on DATETIME,
    execution_time INTEGER,
    success BOOLEAN,
    query_results VARCHAR
)
"""

LEGACY_ROWS = [
    (
        "1.0",
        1,
        0,
        1,
        "a.exm",
        "NOSQL",
        "/srv/schema/V1_0__a.exm",
        b"x",
        "ops",
        "2021-06-16 09:57:22.123456",
        1,
        1,
        "[]",
    ),
    ("1.1", 1, 1, 2, "b.exm", "NOSQL", "C:\\schema\\V1_1__b.exm", b"y", "ops", "2021-06-17 10:00:00", 2, 0, "[]"),
]


def make_schema(version, success=True):
    scmver = SchemaVersion(version)
    scmver.success = success
    return scmver


@pytest.fixture
def db_url(tmp_path):
    """pytest fixture for providing a file-backed SQLite URL in a temporary directory"""
    return f"sqlite:///{tmp_path / 'esmigrate.db'}"


@pytest.fixture
async def db_manager(db_url):
    """pytest fixture for providing a connected DBManager on an empty database"""
    async with DBManager.connect(db_url) as db:
        yield db


@pytest.fixture
async def db_with_success_row(db_manager):
    """pytest fixture for providing populated table with a single `success=true` entry"""
    await db_manager.insert_new_schema(make_schema("1.0"))
    return db_manager


@pytest.fixture
async def db_with_failed_row(db_manager):
    """pytest fixture for providing populated table with a single `success=false` entry"""
    await db_manager.insert_new_schema(make_schema("1.0", success=False))
    return db_manager


@pytest.mark.parametrize(
    ("db_url", "expected"),
    [
        ("sqlite:///esmigrate.db", "sqlite+aiosqlite"),
        ("postgresql://user@host/db", "postgresql+asyncpg"),
        ("postgres://user@host/db", "postgresql+asyncpg"),
        ("mysql://user@host/db", "mysql+aiomysql"),
        ("mariadb://user@host/db", "mysql+aiomysql"),
        ("postgresql+psycopg://user@host/db", "postgresql+psycopg"),
    ],
)
def test_to_async_url_selects_async_driver(db_url, expected):
    """Test fails if to_async_url does not map bare dialects to async drivers or keeps explicit drivers"""
    assert to_async_url(db_url).drivername == expected


@pytest.mark.parametrize("db_url", ["invalid_db_url", "oracle://user@host/db"])
def test_to_async_url_rejects_invalid_or_unsupported_urls(db_url):
    """Test fails if to_async_url accepts malformed URLs or unsupported databases"""
    with pytest.raises(InvalidDBConnectionError):
        to_async_url(db_url)


async def test_db_manager_rejects_sync_driver(tmp_path):
    """Test fails if connect accepts an explicitly configured sync-only driver"""
    with pytest.raises(InvalidDBConnectionError, match="Unsupported database driver"):
        async with DBManager.connect(f"sqlite+pysqlite:///{tmp_path / 'sync.db'}"):
            pass


async def test_db_manager_reports_missing_driver_extra(mocker):
    """Test fails if a missing optional driver does not point to the matching install extra"""
    missing = ModuleNotFoundError("No module named 'asyncpg'", name="asyncpg")
    mocker.patch("esmigrate.internals.db_manager.create_async_engine", side_effect=missing)
    with pytest.raises(InvalidDBConnectionError, match=r"elastic-migrate\[postgres\]"):
        async with DBManager.connect("postgresql://user@host/db"):
            pass


async def test_db_manager_reports_missing_unknown_module(mocker):
    """Test fails if a missing module without a known extra is not reported"""
    missing = ModuleNotFoundError("No module named 'unknown'", name="unknown")
    mocker.patch("esmigrate.internals.db_manager.create_async_engine", side_effect=missing)
    with pytest.raises(InvalidDBConnectionError, match=r"Database driver not installed: unknown$"):
        async with DBManager.connect("postgresql://user@host/db"):
            pass


async def test_db_manager_reports_unreachable_database(tmp_path):
    """Test fails if connect does not raise a connection error when the database cannot be opened"""
    with pytest.raises(InvalidDBConnectionError):
        async with DBManager.connect(f"sqlite:///{tmp_path / 'missing' / 'esmigrate.db'}"):
            pass


async def test_db_manager_reports_refused_server_connection():
    """Test fails if a refused PostgreSQL connection (raised as OSError by asyncpg) escapes unwrapped"""
    with pytest.raises(InvalidDBConnectionError, match="ConnectionRefusedError"):
        async with DBManager.connect("postgresql://esmigrate@127.0.0.1:1/esmigrate"):
            pass


async def test_db_manager_disposes_engine_on_exit(db_url, mocker):
    """Test fails if connect does not dispose the engine when the block exits"""
    dispose = mocker.patch("sqlalchemy.ext.asyncio.AsyncEngine.dispose")
    async with DBManager.connect(db_url):
        pass
    dispose.assert_awaited_once()


async def test_db_manager_disposes_engine_on_error(db_url, mocker):
    """Test fails if connect does not dispose the engine when the block raises"""
    dispose = mocker.patch("sqlalchemy.ext.asyncio.AsyncEngine.dispose")
    with pytest.raises(RuntimeError):
        async with DBManager.connect(db_url):
            raise RuntimeError("boom")
    dispose.assert_awaited_once()


async def test_db_manager_creates_table(db_manager):
    """Test fails if db_manager failed to create model during connect"""
    assert await db_manager.schema_version_exists()


async def test_db_manager_finds_by_version(db_with_success_row):
    """Test fails if find_schema_by_version cannot find entry with primary key `1.0`"""
    scmver_read = await db_with_success_row.find_schema_by_version("1.0")
    assert scmver_read.version == "1.0"


async def test_db_manager_cannot_find_entry(db_manager):
    """Test fails if find_schema_by_version does not return None for non existent key"""
    assert await db_manager.find_schema_by_version("invalid_id") is None


async def test_db_manager_finds_latest_schema(db_with_success_row):
    """Test fails if find_latest_schema cannot find latest schema"""
    row = await db_with_success_row.find_latest_schema()
    assert row.installed_rank == 1


async def test_db_manager_finds_no_latest_schema_in_empty_table(db_manager):
    """Test fails if find_latest_schema does not return None for an empty table"""
    assert await db_manager.find_latest_schema() is None


async def test_db_manager_finds_all_schema(db_with_success_row):
    """Test fails if find_all_schema cannot find all records in installed order"""
    await db_with_success_row.insert_new_schema(make_schema("1.1"))
    rows = await db_with_success_row.find_all_schema()
    assert [row.version for row in rows] == ["1.0", "1.1"]


async def test_db_manager_inserts_schema_with_correct_installed_rank(db_with_success_row):
    """Test fails if insert_new_schema cannot assign next installed_rank"""
    scmver = make_schema("1.1")
    await db_with_success_row.insert_new_schema(scmver)
    assert scmver.installed_rank == 2


async def test_db_manager_raises_error_when_inserting_duplicate(db_with_success_row):
    """Test fails if insert_new_schema does not fail integrity violation"""
    with pytest.raises(SchemaVersionSqlDbError, match=r"Version already installed: 1\.0"):
        await db_with_success_row.insert_new_schema(make_schema("1.0"))


async def test_db_manager_raises_error_when_inserting_after_error(db_with_failed_row):
    """Test fails if insert_new_schema does not raise error when inserting after a failed row"""
    with pytest.raises(SchemaVersionSqlDbError, match=r"Failed previous version: 1\.0"):
        await db_with_failed_row.insert_new_schema(make_schema("1.1"))


async def test_db_manager_wraps_insert_errors(db_with_success_row, mocker):
    """Test fails if database errors on insert are not raised as SchemaVersionSqlDbError"""
    error = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))
    mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit", side_effect=error)
    with pytest.raises(SchemaVersionSqlDbError):
        await db_with_success_row.insert_new_schema(make_schema("1.1"))


async def test_db_manager_deletes_all_failed_schema(db_with_failed_row):
    """Test fails if delete_all_failed_schema does not remove the failed row"""
    await db_with_failed_row.delete_all_failed_schema()
    assert len(await db_with_failed_row.find_all_schema()) == 0


async def test_db_manager_keeps_successful_rows_when_deleting_failed(db_with_success_row):
    """Test fails if delete_all_failed_schema removes successful rows"""
    await db_with_success_row.delete_all_failed_schema()
    assert len(await db_with_success_row.find_all_schema()) == 1


async def test_db_manager_deletes_schema_from_cutoff_rank(db_with_success_row):
    """Test fails if delete_all_schema does not remove rows at or above the cutoff rank"""
    await db_with_success_row.insert_new_schema(make_schema("1.1"))
    await db_with_success_row.delete_all_schema(cutoff_rank=2)
    assert [row.version for row in await db_with_success_row.find_all_schema()] == ["1.0"]


async def test_db_manager_deletes_all_schema(db_with_success_row):
    """Test fails if delete_all_schema does not remove every row by default"""
    await db_with_success_row.delete_all_schema()
    assert len(await db_with_success_row.find_all_schema()) == 0


async def test_db_manager_wraps_delete_errors(db_with_success_row, mocker):
    """Test fails if delete errors are not raised as SchemaVersionSqlDbError"""
    error = OperationalError("DELETE", {}, Exception("database is locked"))
    mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=error)
    with pytest.raises(SchemaVersionSqlDbError):
        await db_with_success_row.delete_all_schema()


def create_legacy_db(path, rows=LEGACY_ROWS):
    with sqlite3.connect(path) as conn:
        conn.execute(LEGACY_TABLE_DDL)
        conn.executemany(f"INSERT INTO esm_schema_version VALUES ({', '.join('?' * 13)})", rows)
    conn.close()


def table_names(path):
    with sqlite3.connect(path) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    return names


async def test_db_manager_round_trips_installed_on_as_utc(db_manager):
    """Test fails if installed_on is not returned as UTC-aware with microseconds preserved"""
    scmver = make_schema("1.0")
    scmver.installed_on = datetime(2026, 10, 24, 1, 2, 3, 456789, tzinfo=UTC)
    await db_manager.insert_new_schema(scmver)
    row = await db_manager.find_schema_by_version("1.0")
    assert row.installed_on == datetime(2026, 10, 24, 1, 2, 3, 456789, tzinfo=UTC)
    assert row.installed_on.tzinfo == UTC


async def test_db_manager_isolates_namespaces(db_url):
    """Test fails if versions, ranks, lookups and deletes leak between namespaces"""
    async with (
        DBManager.connect(db_url, namespace="alpha") as alpha,
        DBManager.connect(db_url, namespace="beta") as beta,
    ):
        await alpha.insert_new_schema(make_schema("1.0"))
        await alpha.insert_new_schema(make_schema("1.1"))
        await beta.insert_new_schema(make_schema("1.0", success=False))
        beta_latest, alpha_latest = await beta.find_latest_schema(), await alpha.find_latest_schema()
        assert beta_latest is not None
        assert alpha_latest is not None
        assert beta_latest.installed_rank == 1
        assert alpha_latest.version == "1.1"
        assert [row.version for row in await beta.find_all_schema()] == ["1.0"]
        assert (await beta.find_schema_by_version("1.1")) is None
        await alpha.insert_new_schema(make_schema("1.2"))
        await beta.delete_all_failed_schema()
        await alpha.delete_all_schema(cutoff_rank=3)
        assert [row.version for row in await alpha.find_all_schema()] == ["1.0", "1.1"]
        assert await beta.find_all_schema() == []


async def test_db_manager_rejects_legacy_table_without_upgrade(tmp_path):
    """Test fails if connect does not refuse a v1 table unless an upgrade is requested"""
    path = tmp_path / "legacy.db"
    create_legacy_db(path)
    with pytest.raises(LegacySchemaTableError, match="esmigrate init"):
        async with DBManager.connect(f"sqlite:///{path}"):
            pass
    assert LEGACY_BACKUP_TABLE not in table_names(path)


async def test_db_manager_upgrades_legacy_table(tmp_path):
    """Test fails if init-style upgrade does not migrate v1 rows into the default namespace and keep a backup"""
    path = tmp_path / "legacy.db"
    create_legacy_db(path)
    async with DBManager.connect(f"sqlite:///{path}", upgrade=True) as db:
        assert db.upgraded_legacy_table
        rows = await db.find_all_schema()
    assert [(row.namespace, row.version, row.script, row.success) for row in rows] == [
        ("default", "1.0", "V1_0__a.exm", True),
        ("default", "1.1", "V1_1__b.exm", False),
    ]
    installed_on = rows[0].installed_on
    assert installed_on is not None
    assert installed_on.tzinfo == UTC
    assert installed_on.microsecond == 123456
    assert LEGACY_BACKUP_TABLE in table_names(path)
    async with DBManager.connect(f"sqlite:///{path}") as db:
        assert not db.upgraded_legacy_table
        assert len(await db.find_all_schema()) == 2


async def test_db_manager_upgrades_empty_legacy_table(tmp_path):
    """Test fails if an empty v1 table cannot be upgraded"""
    path = tmp_path / "legacy.db"
    create_legacy_db(path, rows=[])
    async with DBManager.connect(f"sqlite:///{path}", upgrade=True) as db:
        assert await db.find_all_schema() == []


async def test_db_manager_refuses_upgrade_when_backup_exists(tmp_path):
    """Test fails if the upgrade overwrites an existing backup table"""
    path = tmp_path / "legacy.db"
    create_legacy_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute(f"CREATE TABLE {LEGACY_BACKUP_TABLE} (version VARCHAR)")
    conn.close()
    with pytest.raises(SchemaVersionSqlDbError, match="already exists"):
        async with DBManager.connect(f"sqlite:///{path}", upgrade=True):
            pass


async def test_db_manager_wraps_upgrade_errors(tmp_path, mocker):
    """Test fails if database errors during the legacy upgrade are not raised as SchemaVersionSqlDbError"""
    path = tmp_path / "legacy.db"
    create_legacy_db(path)
    error = OperationalError("CREATE TABLE", {}, Exception("disk I/O error"))
    mocker.patch("esmigrate.internals.db_manager.upgrade_legacy_table", side_effect=error)
    with pytest.raises(SchemaVersionSqlDbError, match="Legacy table upgrade failed"):
        async with DBManager.connect(f"sqlite:///{path}", upgrade=True):
            pass


async def test_db_manager_upgrade_is_noop_for_current_table(db_url):
    """Test fails if upgrade=True changes a database that already uses the current layout"""
    async with DBManager.connect(db_url) as db:
        await db.insert_new_schema(make_schema("1.0"))
    async with DBManager.connect(db_url, upgrade=True) as db:
        assert not db.upgraded_legacy_table
        assert len(await db.find_all_schema()) == 1


def test_upgrade_legacy_row_converts_naive_local_time_to_utc():
    """Test fails if a naive v1 timestamp is not interpreted as local time and converted to UTC"""
    local = datetime(2021, 6, 16, 9, 57, 22)
    values = upgrade_legacy_row({"version": "1.0", "installed_on": local, "script": None, "success": None})
    assert values["installed_on"] == local.astimezone(UTC)
    assert values["namespace"] == "default"
    assert values["script"] is None
    assert values["success"] is None


def test_upgrade_legacy_row_keeps_missing_install_time():
    """Test fails if a v1 row without installed_on gets a fabricated timestamp"""
    assert upgrade_legacy_row({"version": "1.0", "installed_on": None})["installed_on"] is None


async def test_db_manager_reports_table_creation_errors(db_url, mocker):
    """Test fails if errors while creating the table are not raised as InvalidDBConnectionError"""
    error = OperationalError("CREATE TABLE", {}, Exception("permission denied"))
    mocker.patch("esmigrate.models.base.Base.metadata.create_all", side_effect=error)
    with pytest.raises(InvalidDBConnectionError, match="permission denied"):
        async with DBManager.connect(db_url):
            pass
