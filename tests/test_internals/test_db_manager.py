import getpass
import re
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from esmigrate.commons import Direction, Migration, MigVersion, ScriptData
from esmigrate.exceptions import (
    InvalidDBConnectionError,
    InvalidSchemaTableError,
    LegacySchemaTableError,
    SchemaVersionSqlDbError,
)
from esmigrate.internals import DBManager, Layout, create_tables_sql
from esmigrate.internals.db_manager import LEGACY_TABLE, ScriptRun, to_async_url

V1_TABLE_DDL = """
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

V2_TABLE_DDL = """
CREATE TABLE esm_schema_version (
    namespace VARCHAR(64) NOT NULL,
    version VARCHAR(64) NOT NULL,
    version_base INTEGER,
    version_rank INTEGER,
    installed_rank INTEGER,
    description VARCHAR(255),
    type VARCHAR(16),
    script VARCHAR(1024),
    checksum BLOB,
    installed_by VARCHAR(255),
    installed_on DATETIME,
    execution_time INTEGER,
    success BOOLEAN,
    query_results TEXT,
    PRIMARY KEY (namespace, version),
    UNIQUE (namespace, installed_rank)
)
"""

V1_ROWS = [
    (
        "1.0",
        9,
        9,
        1,
        "a.esm",
        "NOSQL",
        "/srv/schema/V1_0__a.esm",
        b"x",
        "ops",
        "2021-06-16 09:57:22.123456",
        1,
        1,
        "r1",
    ),
    ("1.1", 9, 9, 2, "b.esm", "NOSQL", "C:\\schema\\V1_1__b.esm", b"y", "ops", "2021-06-17 10:00:00", 2, 0, "r2"),
    ("1.2", 9, 9, 3, "c.esm", "NOSQL", None, None, "ops", None, None, None, None),
]

V2_ROWS = [
    ("beta", "2.0", 9, 9, 1, "c.esm", "NOSQL", "V2_0__c.esm", b"z", "ci", "2021-06-18 08:00:00.000000", 4, 1, "r3"),
    (
        "alpha",
        "1.1",
        9,
        9,
        2,
        "b.esm",
        "NOSQL",
        "V1_1__b.esm",
        b"y",
        "ops",
        "2021-06-17 10:00:00.000000",
        None,
        0,
        "r2",
    ),
    ("alpha", "1.0", 9, 9, 1, "a.esm", "NOSQL", "V1_0__a.esm", b"x", "ops", "2021-06-16 09:57:22.123456", 1, 1, "r1"),
    ("beta", "2.1", 9, 9, None, "d.esm", "NOSQL", "V2_1__d.esm", None, "ci", None, 0, 1, None),
]


def script(version, direction, content="PUT /twitter"):
    segment = f".{direction}" if direction else ""
    path = f"V{version.base}_{version.rank}__twitter{segment}.esm"
    return ScriptData(version, "twitter", "esm", path, content, direction)


def migration(text="1.0", up=True, down=True):
    version = MigVersion.parse(text)
    return Migration(
        up=script(version, Direction.UP) if up else None,
        down=script(version, Direction.DOWN, "DELETE /twitter") if down else None,
    )


async def record(db, text="1.0", success=True):
    run = await db.start_run(Direction.UP, migration(text))
    await db.finish_run(run, success, 5, f"results {text}")
    return run


def sqlite_path(db_url):
    return db_url.removeprefix("sqlite:///")


def query(db_url, sql):
    with sqlite3.connect(sqlite_path(db_url)) as conn:
        rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def execute(db_url, *statements):
    with sqlite3.connect(sqlite_path(db_url)) as conn:
        for statement in statements:
            conn.executescript(statement)
    conn.close()


def create_old_table(db_url, ddl, rows):
    execute(db_url, ddl)
    with sqlite3.connect(sqlite_path(db_url)) as conn:
        conn.executemany(f"INSERT INTO esm_schema_version VALUES ({', '.join('?' * len(rows[0]))})", rows)
    conn.close()


def table_names(db_url):
    return {row[0] for row in query(db_url, "SELECT name FROM sqlite_master WHERE type = 'table'")}


def state_rows(db_url):
    return query(
        db_url,
        "SELECT namespace, version_base, version_rank, installed_rank, success, execution_time, query_results "
        "FROM esm_schema_state ORDER BY namespace, installed_rank",
    )


def history_rows(db_url):
    return query(
        db_url,
        "SELECT namespace, version_base, version_rank, operation, success, execution_time, query_results "
        "FROM esm_schema_history ORDER BY id",
    )


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
    await record(db_manager)
    return db_manager


@pytest.fixture
async def db_with_failed_row(db_manager):
    """pytest fixture for providing populated table with a single `success=false` entry"""
    await record(db_manager, success=False)
    return db_manager


@pytest.mark.parametrize(
    ("db_url", "expected"),
    [
        ("sqlite:///esmigrate.db", "sqlite+aiosqlite"),
        ("postgresql://user@host/db", "postgresql+asyncpg"),
        ("postgres://user@host/db", "postgresql+asyncpg"),
        ("mysql://user@host/db", "mysql+asyncmy"),
        ("mariadb://user@host/db", "mysql+asyncmy"),
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
    dispose = mocker.spy(AsyncEngine, "dispose")
    async with DBManager.connect(db_url):
        pass
    assert dispose.call_count == 1


async def test_db_manager_disposes_engine_on_error(db_url, mocker):
    """Test fails if connect does not dispose the engine when the block raises"""
    dispose = mocker.spy(AsyncEngine, "dispose")
    with pytest.raises(RuntimeError):
        async with DBManager.connect(db_url):
            raise RuntimeError("boom")
    assert dispose.call_count == 1


async def test_db_manager_wraps_driver_argument_errors():
    """Test fails if a driver rejecting URL arguments crashes with TypeError instead of a connection error"""
    with pytest.raises(InvalidDBConnectionError, match=r"TypeError: .*unexpected keyword argument 'options'"):
        async with DBManager.connect("postgresql://u:p@127.0.0.1:1/db?options=-csearch_path%3Dx"):
            pass


async def test_db_manager_creates_state_and_history_tables(db_manager, db_url):
    """Test fails if connect does not create both tables, and only them, on an empty database"""
    assert db_manager.upgraded_from is Layout.CURRENT
    assert table_names(db_url) == {"esm_schema_state", "esm_schema_history"}


async def test_db_manager_reports_table_creation_errors(db_url, mocker):
    """Test fails if a failed table creation is not a connection error pointing to init --print-sql"""
    error = OperationalError("CREATE TABLE", {}, Exception("permission denied"))
    mocker.patch("esmigrate.models.base.Base.metadata.create_all", side_effect=error)
    with pytest.raises(InvalidDBConnectionError, match=r"(?s)permission denied.*`esmigrate init --print-sql`"):
        async with DBManager.connect(db_url):
            pass


async def test_db_manager_uses_configured_schema(db_url):
    """Test fails if the tables are not created and queried in the configured schema"""
    async with DBManager.connect(db_url, schema="main") as db:
        assert db.schema == "main"
        await record(db)
        assert [row.version for row in await db.find_all_schema()] == [MigVersion(1, 0)]
    assert table_names(db_url) == {"esm_schema_state", "esm_schema_history"}


async def test_db_manager_reports_missing_schema(db_url):
    """Test fails if a schema that does not exist is not reported as a connection error"""
    with pytest.raises(InvalidDBConnectionError, match="Database schema missing_schema does not exist"):
        async with DBManager.connect(db_url, schema="missing_schema"):
            pass


async def test_db_manager_needs_no_ddl_for_tables_created_from_printed_sql(db_url):
    """Test fails if tables created by a DBA from the printed SQL still need DDL rights to connect"""
    execute(db_url, create_tables_sql(db_url))
    async with DBManager.connect(f"sqlite:///file:{sqlite_path(db_url)}?mode=ro&uri=true") as db:
        assert await db.find_latest_schema() is None
    async with DBManager.connect(db_url) as db:
        await record(db)
    assert state_rows(db_url) == [("default", 1, 0, 1, 1, 5, "results 1.0")]


async def test_db_manager_reports_missing_columns_in_both_tables(db_url):
    """Test fails if missing columns are not listed for every table before anything runs"""
    execute(
        db_url,
        create_tables_sql(db_url),
        "ALTER TABLE esm_schema_state DROP COLUMN checksum",
        "ALTER TABLE esm_schema_history DROP COLUMN script",
        "ALTER TABLE esm_schema_history DROP COLUMN executed_by",
    )
    with pytest.raises(InvalidSchemaTableError) as raised:
        async with DBManager.connect(db_url):
            pass
    assert str(raised.value) == (
        "Schema tables are missing columns:\n  esm_schema_state: checksum\n  esm_schema_history: executed_by, script"
    )


async def test_db_manager_accepts_upper_case_and_extra_columns(db_url):
    """Test fails if DBA-created tables with upper-case names or extra columns are refused"""
    execute(
        db_url,
        create_tables_sql(db_url).upper(),
        "ALTER TABLE esm_schema_state ADD COLUMN audit_tag VARCHAR(8)",
    )
    async with DBManager.connect(db_url) as db:
        await record(db)
        assert [row.version for row in await db.find_all_schema()] == [MigVersion(1, 0)]


@pytest.mark.parametrize(("ddl", "rows", "layout"), [(V1_TABLE_DDL, V1_ROWS, "V1"), (V2_TABLE_DDL, V2_ROWS, "V2")])
async def test_db_manager_refuses_old_layout_without_upgrade(db_url, ddl, rows, layout):
    """Test fails if a v1 or v2 table with rows is not refused, without changes, unless init asks for the copy"""
    create_old_table(db_url, ddl, rows)
    with pytest.raises(LegacySchemaTableError, match=f"use the {layout} layout, run `esmigrate init`"):
        async with DBManager.connect(db_url):
            pass
    assert table_names(db_url) == {LEGACY_TABLE}


@pytest.mark.parametrize("ddl", [V1_TABLE_DDL, V2_TABLE_DDL])
async def test_db_manager_treats_empty_old_table_as_current(db_url, ddl):
    """Test fails if an empty v1 or v2 table blocks commands or is changed"""
    execute(db_url, ddl)
    async with DBManager.connect(db_url) as db:
        assert db.upgraded_from is Layout.CURRENT
        await record(db)
    assert query(db_url, "SELECT count(*) FROM esm_schema_version") == [(0,)]


async def test_db_manager_copies_v1_rows(db_url):
    """Test fails if v1 rows are not copied into the default namespace with file names, milliseconds and UTC times"""
    create_old_table(db_url, V1_TABLE_DDL, V1_ROWS)
    async with DBManager.connect(db_url, upgrade=True) as db:
        assert db.upgraded_from is Layout.V1
        rows = await db.find_all_schema()
        history = await db.find_history()
    assert [(row.namespace, row.version, row.installed_rank) for row in rows] == [
        ("default", MigVersion(1, 0), 1),
        ("default", MigVersion(1, 1), 2),
        ("default", MigVersion(1, 2), 3),
    ]
    assert [row.script for row in rows] == ["V1_0__a.esm", "V1_1__b.esm", None]
    assert [row.success for row in rows] == [True, False, None]
    assert [row.execution_time for row in rows] == [1000, 2000, None]
    assert [row.checksum for row in rows] == [b"x", b"y", None]
    assert [row.installed_on for row in rows] == [
        datetime(2021, 6, 16, 9, 57, 22, 123456).astimezone(UTC),
        datetime(2021, 6, 17, 10, 0).astimezone(UTC),
        None,
    ]
    assert [(entry.operation, entry.version_base, entry.version_rank) for entry in history] == [
        ("up", 1, 0),
        ("up", 1, 1),
        ("up", 1, 2),
    ]
    first, row = history[0], rows[0]
    assert (first.description, first.script, first.checksum) == (row.description, row.script, row.checksum)
    assert (first.executed_by, first.executed_on) == (row.installed_by, row.installed_on)
    assert (first.execution_time, first.success, first.query_results) == (1000, True, "r1")
    assert query(db_url, "SELECT version FROM esm_schema_version ORDER BY version") == [("1.0",), ("1.1",), ("1.2",)]


@pytest.mark.usefixtures("local_time_plus_six")
async def test_db_manager_copies_v2_rows(db_url):
    """Test fails if v2 rows lose their namespace or script, or their UTC times are shifted"""
    create_old_table(db_url, V2_TABLE_DDL, V2_ROWS)
    async with DBManager.connect(db_url, upgrade=True, namespace="alpha") as db:
        assert db.upgraded_from is Layout.V2
        alpha = await db.find_all_schema()
    assert [(row.version, row.script, row.success, row.execution_time) for row in alpha] == [
        (MigVersion(1, 0), "V1_0__a.esm", True, 1000),
        (MigVersion(1, 1), "V1_1__b.esm", False, None),
    ]
    assert alpha[0].installed_on == datetime(2021, 6, 16, 9, 57, 22, 123456, tzinfo=UTC)
    assert history_rows(db_url) == [
        ("alpha", 1, 0, "up", 1, 1000, "r1"),
        ("alpha", 1, 1, "up", 0, None, "r2"),
        ("beta", 2, 1, "up", 1, 0, None),
        ("beta", 2, 0, "up", 1, 4000, "r3"),
    ]


async def test_db_manager_copies_old_rows_only_once(db_url):
    """Test fails if a second init or a reset after the upgrade copies the old rows again"""
    create_old_table(db_url, V2_TABLE_DDL, V2_ROWS)
    async with DBManager.connect(db_url, upgrade=True, namespace="alpha"):
        pass
    async with DBManager.connect(db_url, upgrade=True, namespace="alpha") as db:
        assert db.upgraded_from is Layout.CURRENT
        await db.delete_all_schema()
    async with DBManager.connect(db_url, upgrade=True, namespace="alpha") as db:
        assert db.upgraded_from is Layout.CURRENT
        assert await db.find_all_schema() == []
    assert len(history_rows(db_url)) == len(V2_ROWS)


async def test_db_manager_copies_old_rows_in_configured_schema(db_url):
    """Test fails if the copy does not read the old table from the configured schema"""
    create_old_table(db_url, V1_TABLE_DDL, V1_ROWS)
    async with DBManager.connect(db_url, upgrade=True, schema="main") as db:
        assert db.upgraded_from is Layout.V1
        assert len(await db.find_all_schema()) == len(V1_ROWS)


async def test_db_manager_refuses_copy_of_unusable_versions(db_url):
    """Test fails if unparseable, out-of-range or colliding versions are not all listed before anything is copied"""
    row = ("NOSQL", "V.esm", None, "ops", None, 1, 1, None)
    rows = [
        ("default", "1.01", 1, 0, 1, "a.esm", *row),
        ("other", "1.01", 1, 0, 1, "a.esm", *row),
        ("default", "1.1", 1, 1, 2, "b.esm", *row),
        ("default", "abc", 1, 2, 3, "c.esm", *row),
        ("default", "99999999999.0", 1, 3, 4, "d.esm", *row),
    ]
    create_old_table(db_url, V2_TABLE_DDL, rows)
    with pytest.raises(SchemaVersionSqlDbError) as raised:
        async with DBManager.connect(db_url, upgrade=True):
            pass
    assert str(raised.value) == (
        "Cannot copy existing schema versions:\n"
        "  default: 1.01 and 1.1 are the same version\n"
        "  default: Schema version 99999999999.0 is out of range: [0, 2147483647]\n"
        "  default: Invalid version: abc"
    )
    assert state_rows(db_url) == []
    assert history_rows(db_url) == []
    assert query(db_url, "SELECT count(*) FROM esm_schema_version") == [(5,)]


async def test_db_manager_wraps_copy_errors(db_url, mocker):
    """Test fails if database errors during the copy are not raised as SchemaVersionSqlDbError"""
    create_old_table(db_url, V1_TABLE_DDL, V1_ROWS)
    error = OperationalError("INSERT", {}, Exception("disk I/O error"))
    mocker.patch("esmigrate.internals.db_manager.copy_old_rows", side_effect=error)
    with pytest.raises(SchemaVersionSqlDbError, match="Copying existing schema versions failed"):
        async with DBManager.connect(db_url, upgrade=True):
            pass


async def test_db_manager_commits_the_start_of_an_up_run(db_manager, db_url):
    """Test fails if starting an up run does not commit a running state row and history row with the up script"""
    run = await db_manager.start_run(Direction.UP, migration())
    assert run == ScriptRun(Direction.UP, MigVersion(1, 0), run.history_id)
    assert state_rows(db_url) == [("default", 1, 0, 1, None, None, None)]
    assert history_rows(db_url) == [("default", 1, 0, "up", None, None, None)]
    (entry,) = await db_manager.find_history()
    assert (entry.id, entry.script, entry.description) == (run.history_id, "V1_0__twitter.up.esm", "twitter.esm")
    assert entry.checksum == script(MigVersion(1, 0), Direction.UP).checksum
    assert entry.executed_by == getpass.getuser()
    assert entry.executed_on is not None
    assert datetime.now(UTC) - entry.executed_on < timedelta(minutes=1)
    (state,) = await db_manager.find_all_schema()
    assert (state.type, state.installed_by, state.installed_on) == ("NOSQL", entry.executed_by, entry.executed_on)


@pytest.mark.parametrize("direction", [None, Direction.UP])
async def test_db_manager_records_the_up_script_in_the_state_row(db_manager, direction):
    """Test fails if the state row does not keep the version, description, path and checksum of the up script"""
    up = script(MigVersion(1, 2), direction)
    await db_manager.start_run(Direction.UP, Migration(up=up))
    (state,) = await db_manager.find_all_schema()
    assert (state.version, state.version_base, state.version_rank) == (MigVersion(1, 2), 1, 2)
    assert (state.description, state.script, state.checksum) == ("twitter.esm", up.path, up.checksum)
    assert state.success is None


async def test_db_manager_records_the_up_script_of_a_pair_in_the_state_row(db_manager):
    """Test fails if the state row of a reversible migration records its down script"""
    pair = migration()
    assert pair.up is not None
    await db_manager.start_run(Direction.UP, pair)
    (state,) = await db_manager.find_all_schema()
    assert (state.script, state.checksum) == (pair.up.path, pair.up.checksum)


async def test_db_manager_gives_next_rank_and_reuses_undone_ranks(db_with_success_row, db_url):
    """Test fails if a new version does not get latest + 1 or an undone start keeps its rank"""
    run = await db_with_success_row.start_run(Direction.UP, migration("1.1"))
    await db_with_success_row.undo_run(run, 2, "error")
    await record(db_with_success_row, "2.0")
    assert [row[3] for row in state_rows(db_url)] == [1, 2]


@pytest.mark.parametrize(("success", "stored"), [(True, 1), (False, 0)])
async def test_db_manager_finishes_an_up_run(db_manager, db_url, success, stored):
    """Test fails if the result, duration and requests of an up run are not stored in both tables"""
    run = await db_manager.start_run(Direction.UP, migration())
    await db_manager.finish_run(run, success, 120, "requests")
    assert state_rows(db_url) == [("default", 1, 0, 1, stored, 120, "requests")]
    assert history_rows(db_url) == [("default", 1, 0, "up", stored, 120, "requests")]


async def test_db_manager_undoes_an_up_run_that_never_reached_elasticsearch(db_manager, db_url):
    """Test fails if an undone up run leaves a state row or loses its failed history row"""
    run = await db_manager.start_run(Direction.UP, migration())
    await db_manager.undo_run(run, 7, "connection error")
    assert state_rows(db_url) == []
    assert history_rows(db_url) == [("default", 1, 0, "up", 0, 7, "connection error")]


async def test_db_manager_commits_the_start_of_a_down_run(db_with_success_row, db_url):
    """Test fails if starting a down run does not mark the row running and record the down script in the history"""
    run = await db_with_success_row.start_run(Direction.DOWN, migration())
    assert run.direction is Direction.DOWN
    assert state_rows(db_url) == [("default", 1, 0, 1, None, 5, "results 1.0")]
    entry = (await db_with_success_row.find_history())[-1]
    assert (entry.operation, entry.success, entry.script) == ("down", None, "V1_0__twitter.down.esm")
    assert entry.checksum == script(MigVersion(1, 0), Direction.DOWN, "DELETE /twitter").checksum


async def test_db_manager_deletes_the_state_row_after_a_successful_down(db_with_success_row, db_url):
    """Test fails if a successful down run does not delete the state row and record the result in the history"""
    run = await db_with_success_row.start_run(Direction.DOWN, migration())
    await db_with_success_row.finish_run(run, True, 9, "down requests")
    assert state_rows(db_url) == []
    assert history_rows(db_url)[-1] == ("default", 1, 0, "down", 1, 9, "down requests")


async def test_db_manager_keeps_the_up_result_after_a_failed_down(db_with_success_row, db_url):
    """Test fails if a failed down run does not mark the state row failed while keeping the up run's details"""
    run = await db_with_success_row.start_run(Direction.DOWN, migration())
    await db_with_success_row.finish_run(run, False, 9, "down requests")
    assert state_rows(db_url) == [("default", 1, 0, 1, 0, 5, "results 1.0")]
    assert history_rows(db_url)[-1] == ("default", 1, 0, "down", 0, 9, "down requests")


async def test_db_manager_restores_the_state_row_after_an_undone_down(db_with_success_row, db_url):
    """Test fails if an undone down run does not set the state row back to applied"""
    run = await db_with_success_row.start_run(Direction.DOWN, migration())
    await db_with_success_row.undo_run(run, 3, "connection error")
    assert state_rows(db_url) == [("default", 1, 0, 1, 1, 5, "results 1.0")]
    assert history_rows(db_url)[-1] == ("default", 1, 0, "down", 0, 3, "connection error")


async def test_db_manager_records_down_only_migration_without_script(db_manager):
    """Test fails if a down-only migration is not recorded by upgrade with its version and empty script and checksum"""
    run = await db_manager.start_run(Direction.UP, migration(up=False))
    await db_manager.finish_run(run, True, 0, "")
    (row,) = await db_manager.find_all_schema()
    (entry,) = await db_manager.find_history()
    assert (row.version, row.description) == (MigVersion(1, 0), "twitter.esm")
    assert (row.script, row.checksum, row.success) == (None, None, True)
    assert (entry.script, entry.checksum, entry.success) == (None, None, True)


@pytest.mark.parametrize("direction", list(Direction))
async def test_db_manager_refuses_to_start_after_a_failed_row(db_with_failed_row, db_url, direction):
    """Test fails if any run can start while the latest row is failed"""
    with pytest.raises(SchemaVersionSqlDbError, match=r"Failed previous version: 1\.0"):
        await db_with_failed_row.start_run(direction, migration("1.0" if direction is Direction.DOWN else "1.1"))
    assert len(history_rows(db_url)) == 1


@pytest.mark.parametrize("direction", list(Direction))
async def test_db_manager_refuses_to_start_after_an_interrupted_row(db_manager, db_url, direction):
    """Test fails if any run can start while the latest row was interrupted"""
    await db_manager.start_run(Direction.UP, migration())
    with pytest.raises(SchemaVersionSqlDbError, match=r"Failed previous version: 1\.0"):
        await db_manager.start_run(direction, migration("1.0" if direction is Direction.DOWN else "1.1"))
    assert len(history_rows(db_url)) == 1


async def test_db_manager_refuses_to_start_an_installed_version(db_with_success_row):
    """Test fails if an up run can start for a version that is already applied"""
    with pytest.raises(SchemaVersionSqlDbError, match=r"Version already installed: 1\.0"):
        await db_with_success_row.start_run(Direction.UP, migration())


@pytest.mark.parametrize("versions", [[], ["1.0", "1.1"]])
async def test_db_manager_refuses_a_down_run_below_the_latest_version(db_manager, db_url, versions):
    """Test fails if a down run can start for a version that is not the latest applied one"""
    for version in versions:
        await record(db_manager, version)
    with pytest.raises(SchemaVersionSqlDbError, match=r"Version is not the latest applied: 1\.0"):
        await db_manager.start_run(Direction.DOWN, migration())
    assert [row[4] for row in state_rows(db_url)] == [1] * len(versions)


async def test_db_manager_rolls_back_a_failed_start(db_manager, db_url, mocker):
    """Test fails if a failed start leaves a state row behind or escapes as a raw database error"""
    error = IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))
    mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit", side_effect=error)
    with pytest.raises(SchemaVersionSqlDbError, match="UNIQUE constraint failed"):
        await db_manager.start_run(Direction.UP, migration())
    mocker.stopall()
    assert state_rows(db_url) == []
    assert history_rows(db_url) == []


async def test_db_manager_leaves_the_run_interrupted_when_the_result_cannot_be_written(db_manager, db_url):
    """Test fails if a failed result write changes the state row or puts request bodies in the error"""
    run = await db_manager.start_run(Direction.UP, migration())
    execute(db_url, "CREATE TRIGGER boom BEFORE UPDATE ON esm_schema_history BEGIN SELECT RAISE(ABORT, 'boom'); END")
    with pytest.raises(SchemaVersionSqlDbError, match="boom") as raised:
        await db_manager.finish_run(run, True, 5, "secret-response-body")
    assert "secret-response-body" not in str(raised.value)
    assert state_rows(db_url) == [("default", 1, 0, 1, None, None, None)]


async def test_db_manager_finds_by_version(db_with_success_row):
    """Test fails if find_schema_by_version cannot find the row for an applied version"""
    row = await db_with_success_row.find_schema_by_version(MigVersion(1, 0))
    assert row is not None
    assert row.version == MigVersion(1, 0)


async def test_db_manager_cannot_find_entry(db_with_success_row):
    """Test fails if find_schema_by_version does not return None for a version that was never applied"""
    assert await db_with_success_row.find_schema_by_version(MigVersion(9, 9)) is None


async def test_db_manager_finds_latest_schema(db_with_success_row):
    """Test fails if find_latest_schema cannot find latest schema"""
    row = await db_with_success_row.find_latest_schema()
    assert row is not None
    assert row.installed_rank == 1


async def test_db_manager_finds_no_latest_schema_in_empty_table(db_manager):
    """Test fails if find_latest_schema does not return None for an empty table"""
    assert await db_manager.find_latest_schema() is None


async def test_db_manager_finds_all_schema(db_with_success_row):
    """Test fails if find_all_schema cannot find all records in installed order"""
    await record(db_with_success_row, "1.1")
    rows = await db_with_success_row.find_all_schema()
    assert [row.version for row in rows] == [MigVersion(1, 0), MigVersion(1, 1)]


async def test_db_manager_finds_applied_versions(db_with_success_row):
    """Test fails if find_applied_versions does not return every recorded version"""
    await record(db_with_success_row, "1.10")
    assert await db_with_success_row.find_applied_versions() == {MigVersion(1, 0), MigVersion(1, 10)}


async def test_db_manager_keeps_history_after_rows_are_deleted(db_with_success_row, db_url):
    """Test fails if deleting state rows also deletes their history"""
    await db_with_success_row.delete_all_schema()
    assert len(await db_with_success_row.find_history()) == 1
    assert state_rows(db_url) == []


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
    await record(db_with_success_row, "1.1")
    await db_with_success_row.delete_all_schema(cutoff_rank=2)
    assert [row.version for row in await db_with_success_row.find_all_schema()] == [MigVersion(1, 0)]


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


async def test_db_manager_round_trips_installed_on_as_utc(db_with_success_row):
    """Test fails if installed_on is not returned as a UTC-aware start time"""
    row = await db_with_success_row.find_schema_by_version(MigVersion(1, 0))
    assert row is not None
    assert row.installed_on is not None
    assert row.installed_on.tzinfo == UTC
    assert datetime.now(UTC) - row.installed_on < timedelta(minutes=1)


async def test_db_manager_isolates_namespaces(db_url):
    """Test fails if versions, ranks, history, lookups and deletes leak between namespaces"""
    async with (
        DBManager.connect(db_url, namespace="alpha") as alpha,
        DBManager.connect(db_url, namespace="beta") as beta,
    ):
        await record(alpha, "1.0")
        await record(alpha, "1.1")
        await record(beta, "1.0", success=False)
        beta_latest, alpha_latest = await beta.find_latest_schema(), await alpha.find_latest_schema()
        assert beta_latest is not None
        assert alpha_latest is not None
        assert beta_latest.installed_rank == 1
        assert alpha_latest.version == MigVersion(1, 1)
        assert [row.version for row in await beta.find_all_schema()] == [MigVersion(1, 0)]
        assert await beta.find_schema_by_version(MigVersion(1, 1)) is None
        assert await beta.find_applied_versions() == {MigVersion(1, 0)}
        assert [entry.namespace for entry in await beta.find_history()] == ["beta"]
        await record(alpha, "1.2")
        await beta.delete_all_failed_schema()
        await alpha.delete_all_schema(cutoff_rank=3)
        assert [row.version for row in await alpha.find_all_schema()] == [MigVersion(1, 0), MigVersion(1, 1)]
        assert await beta.find_all_schema() == []


def statements(sql):
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


@pytest.mark.parametrize(
    ("db_url", "schema", "prefix"),
    [
        ("sqlite:///esmigrate.db", None, ""),
        ("postgresql://user@host/db", None, ""),
        ("postgresql://user@host/db", "esm", "esm."),
        ("mysql://user@host/db", None, ""),
        ("mysql://user@host/db", "esm", "esm."),
        ("mariadb://user@host/db", "esm", "esm."),
    ],
)
def test_create_tables_sql_prints_both_tables_and_the_index(db_url, schema, prefix):
    """Test fails if the printed SQL is not the two tables and the history index, qualified with the schema"""
    sql = create_tables_sql(db_url, schema)
    parts = statements(sql)
    assert sql.endswith(";")
    assert [re.sub(r"\s*\(.*", "", part, flags=re.S) for part in parts] == [
        f"CREATE TABLE {prefix}esm_schema_state",
        f"CREATE TABLE {prefix}esm_schema_history",
        f"CREATE INDEX ix_esm_schema_history_namespace_id ON {prefix}esm_schema_history",
    ]
    assert "esm_schema_lock" not in sql


@pytest.mark.parametrize("db_url", ["invalid_db_url", "oracle://user@host/db", "postgresql+nosuch://user@host/db"])
def test_create_tables_sql_rejects_invalid_urls_and_drivers(db_url):
    """Test fails if SQL is printed for a URL or driver that a normal run would refuse"""
    with pytest.raises(InvalidDBConnectionError):
        create_tables_sql(db_url)


def test_create_tables_sql_does_not_connect(tmp_path):
    """Test fails if printing the SQL opens the database"""
    create_tables_sql(f"sqlite:///{tmp_path / 'never.db'}")
    assert not (tmp_path / "never.db").exists()
