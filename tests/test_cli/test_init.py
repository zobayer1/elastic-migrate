import pytest

from esmigrate import cli
from esmigrate.exceptions import Errors
from esmigrate.internals import LEGACY_TABLE
from tests.test_cli.helpers import (
    create_legacy_table,
    create_v2_table,
    history_rows,
    invoke,
    raw_rows,
    seed,
    versions,
)


def test_cli_init_cmd_succeeds_when_schema_table_is_empty(runner, context):
    """Test fails if `esmigrate init` does not create an empty schema table"""
    result = invoke(runner, "init")
    assert result.exit_code == 0
    assert "Schema database initialized" in result.output


def test_cli_init_cmd_succeeds_when_schema_exists(runner, context):
    """Test fails if `esmigrate init` does not report the latest installed version"""
    seed(context, ("1.0", True))
    result = invoke(runner, "init")
    assert result.exit_code == 0
    assert "Schema database already initialized at version 1.0" in result.output


def test_cli_init_cmd_fails_with_db_error(runner, context):
    """Test fails if `esmigrate init` does not report an invalid database URL"""
    context.schema_db = "oracle://user@host/db"
    result = invoke(runner, "init")
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED


@pytest.mark.parametrize(("create", "layout"), [(create_legacy_table, "V1"), (create_v2_table, "V2")])
def test_cli_init_cmd_copies_old_table(runner, context, create, layout):
    """Test fails if `esmigrate init` does not copy a v1 or v2 table and report the layout and the kept table"""
    if layout == "V1":
        create(context, [("1.0", 1, 1)])
    else:
        create(context, [("default", "1.0", 1, 1)])
    result = invoke(runner, "init")
    assert result.exit_code == 0, result.output
    assert f"Copied the {layout} schema versions, {LEGACY_TABLE} is kept as the backup" in result.output
    assert "Schema database initialized at version 1.0" in result.output
    assert versions(context) == ["1.0"]
    assert [(entry.operation, entry.success) for entry in history_rows(context)] == [("up", True)]
    assert raw_rows(context, f"SELECT version FROM {LEGACY_TABLE}") == [("1.0",)]


def test_cli_init_cmd_does_not_report_a_copy_for_current_tables(runner, context):
    """Test fails if `esmigrate init` reports copying rows when the tables already use the current layout"""
    seed(context, ("1.0", True))
    result = invoke(runner, "init")
    assert result.exit_code == 0
    assert "Copied" not in result.output


def test_cli_init_cmd_fails_when_rows_cannot_be_copied(runner, context):
    """Test fails if `esmigrate init` copies anything when old versions collapse onto the same version"""
    create_legacy_table(context, [("1.01", 1, 1), ("1.1", 2, 1)])
    result = invoke(runner, "init")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE
    assert "default: 1.01 and 1.1 are the same version" in result.output
    assert raw_rows(context, "SELECT count(*) FROM esm_schema_state") == [(0,)]


def test_cli_init_cmd_prints_sql_without_connecting(runner, context, tmp_path):
    """Test fails if `esmigrate init --print-sql` does not print only the SQL to stdout without opening the database"""
    result = invoke(runner, "init", "--print-sql")
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("CREATE TABLE esm_schema_state (")
    assert "CREATE TABLE esm_schema_history (" in result.stdout
    assert "CREATE INDEX ix_esm_schema_history_namespace_id ON esm_schema_history (namespace, id);" in result.stdout
    assert "Using profile test" in result.stderr
    assert "Using profile" not in result.stdout
    assert not (tmp_path / "esmigrate.db").exists()


def test_cli_init_cmd_prints_sql_for_the_configured_schema(runner, context):
    """Test fails if the printed SQL is not qualified with schema_db_schema for the profile's database"""
    context.schema_db = "postgresql://migrator:secret@db.example.com/esmigrate"
    context.schema_db_schema = "esm"
    result = invoke(runner, "init", "--print-sql")
    assert result.exit_code == 0, result.output
    assert "CREATE TABLE esm.esm_schema_state (" in result.stdout
    assert "id SERIAL NOT NULL" in result.stdout
    assert "ON esm.esm_schema_history (namespace, id);" in result.stdout


def test_cli_init_cmd_print_sql_fails_with_db_error(runner, context):
    """Test fails if `esmigrate init --print-sql` prints SQL for a database URL a normal run would refuse"""
    context.schema_db = "oracle://user@host/db"
    result = invoke(runner, "init", "--print-sql")
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED
    assert "InvalidDBConnectionError: Unsupported database 'oracle', use sqlite, postgresql or mysql" in result.stderr
    assert result.stdout == ""


def test_cli_init_cmd_help_documents_print_sql(runner):
    """Test fails if `esmigrate init --help` does not describe the copy and the --print-sql option"""
    result = runner.invoke(cli.main, ["init", "--help"])
    assert result.exit_code == 0
    assert "copying rows from v1 and v2 tables" in result.stdout
    assert "--print-sql" in result.stdout
