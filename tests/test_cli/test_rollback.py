from esmigrate.exceptions import Errors, SchemaVersionSqlDbError
from tests.test_cli.helpers import (
    invoke,
    seed,
    stored_rows,
)


def test_cli_rollback_cmd_succeeds_when_no_error_entry(runner, context):
    """Test fails if `esmigrate rollback` does not succeed when there is no error in schema db"""
    seed(context, ("1.0", True))
    result = invoke(runner, "rollback")
    assert result.exit_code == 0
    assert "does not have any error entry" in result.output
    assert len(stored_rows(context)) == 1


def test_cli_rollback_cmd_succeeds_with_error_entry(runner, context):
    """Test fails if `esmigrate rollback` does not remove failed entries"""
    seed(context, ("1.0", True), ("1.1", False))
    result = invoke(runner, "rollback")
    assert result.exit_code == 0
    assert "Rollback successful" in result.output
    assert [str(row.version) for row in stored_rows(context)] == ["1.0"]


def test_cli_rollback_cmd_fails_with_sql_db_error(runner, context, mocker):
    """Test fails if `esmigrate rollback` fails to check sql query error"""
    seed(context, ("1.0", False))
    mocker.patch("esmigrate.internals.DBManager.delete_all_failed_schema", side_effect=SchemaVersionSqlDbError)
    result = invoke(runner, "rollback")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE
