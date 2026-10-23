import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from esmigrate.exceptions import InvalidDBConnectionError, SchemaVersionSqlDbError
from esmigrate.internals import DBManager
from esmigrate.internals.db_manager import to_async_url
from esmigrate.models import SchemaVersion


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
