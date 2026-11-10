import getpass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from esmigrate.commons import Direction, Migration, MigVersion
from esmigrate.exceptions import (
    InvalidDBConnectionError,
    InvalidSchemaTableError,
    SchemaVersionSqlDbError,
)
from esmigrate.internals import DBManager, Layout, create_tables_sql
from esmigrate.internals.db_manager import ScriptRun
from tests.test_internals.db_helpers import (
    execute,
    history_rows,
    migration,
    record,
    script,
    sqlite_path,
    state_rows,
    table_names,
)


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


async def test_db_manager_rejects_sync_driver(tmp_path):
    """Test fails if connect accepts an explicitly configured sync-only driver"""
    with pytest.raises(InvalidDBConnectionError, match="Unsupported database driver"):
        async with DBManager.connect(f"sqlite+pysqlite:///{tmp_path / 'sync.db'}"):
            pass


async def test_db_manager_reports_missing_driver_extra(mocker):
    """Test fails if a missing optional driver does not point to the matching install extra"""
    missing = ModuleNotFoundError("No module named 'asyncpg'", name="asyncpg")
    mocker.patch("esmigrate.internals.db_engine.create_async_engine", side_effect=missing)
    with pytest.raises(InvalidDBConnectionError, match=r"elastic-migrate\[postgres\]"):
        async with DBManager.connect("postgresql://user@host/db"):
            pass


async def test_db_manager_reports_missing_unknown_module(mocker):
    """Test fails if a missing module without a known extra is not reported"""
    missing = ModuleNotFoundError("No module named 'unknown'", name="unknown")
    mocker.patch("esmigrate.internals.db_engine.create_async_engine", side_effect=missing)
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
