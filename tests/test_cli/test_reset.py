from esmigrate.exceptions import Errors, SchemaVersionSqlDbError
from tests.test_cli.helpers import (
    invoke,
    seed,
    stored_rows,
)


def test_cli_reset_cmd_succeeds(runner, context):
    """Test fails if `esmigrate reset` does not remove all entries"""
    seed(context, ("1.0", True), ("1.1", False))
    result = invoke(runner, "reset")
    assert result.exit_code == 0
    assert stored_rows(context) == []


def test_cli_reset_cmd_fails_with_sql_db_error(runner, context, mocker):
    """Test fails if `esmigrate reset` fails to check sql query error"""
    mocker.patch("esmigrate.internals.DBManager.delete_all_schema", side_effect=SchemaVersionSqlDbError)
    result = invoke(runner, "reset")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE
