import pytest
from click.testing import CliRunner
from requests import HTTPError, Response

from esmigrate import cli
from esmigrate.commons import Command, ScriptData
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    ElasticsearchConnError,
    Errors,
    InvalidCommandScriptError,
    InvalidDBConnectionError,
    InvalidSchemaFileError,
    SchemaVersionSqlDbError,
)
from esmigrate.internals import ScriptParser
from esmigrate.models import SchemaVersion


@pytest.fixture(scope="module")
def runner():
    """Pytest fixture for testing command line interfaces"""
    return CliRunner()


@pytest.fixture(scope="module")
def context():
    """Pytest fixture for test context"""
    ctx = ContextConfig()
    ctx.profile = "test"
    return ctx


@pytest.fixture(scope="module")
def success_schema():
    """Pytest fixture for successful SchemaModel object"""
    scm = SchemaVersion("1.0")
    scm.success = True
    return scm


@pytest.fixture(scope="module")
def error_schema():
    """Pytest fixture for failed SchemaModel object"""
    scm = SchemaVersion("1.0")
    scm.success = False
    return scm


@pytest.fixture(scope="module")
def script_data():
    """Pytest module for schema script data object"""
    return ScriptData(
        1,
        0,
        "V1_0__create_index_mapping_for_twitter",
        "exm",
        "V1_0__create_index_mapping_for_twitter.exm",
        """PUT twitter
        PUT twitter/_mapping/doc
        {
            "dynamic": "strict",
            "properties": {"username": {"type": "text"}}
        }""",
    )


@pytest.fixture(scope="module")
def http_response():
    """Pytest fixture for creating dummy requests.Response object"""
    response = Response()
    response.status_code = 200
    return response


@pytest.fixture(scope="module")
def http_error():
    """Pytest fixture for creating dummy requests.HTTPError object"""
    error = HTTPError()
    error.response = Response()
    error.response.status_code = 400
    return error


def test_cli_invocation_succeeds(runner):
    """Test fails if `esmigrate` does not return with success"""
    result = runner.invoke(cli.main)
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_help_argument_succeeds(runner):
    """Test fails if `esmigrate --help` does not return with success"""
    result = runner.invoke(cli.main, ["--help"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_version_argument_succeeds(runner):
    """Test fails if `esmigrate --version` does not return with success"""
    result = runner.invoke(cli.main, ["--version"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_config_command_fails_to_load_context_profile(runner):
    """Test fails if `esmigrate --profile {profile} {command}` does not return error"""
    result = runner.invoke(cli.main, ["--profile", "invalid-profile", "config"])
    assert result.exit_code == Errors.ERR_PROFILE_NOT_FOUND


def test_cli_config_command_loads_context_profile(runner, mocker, context):
    """Test fails if `esmigrate --profile {profile} {command}` returns an error"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    result = runner.invoke(cli.main, ["--profile", "invalid-profile", "config"])
    assert result.exit_code == 0
    assert context.profile in result.output


def test_cli_init_cmd_fails_with_db_error(runner, mocker, context):
    """Test fails if `esmigrate init` does not return error when get_db_manager fails"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.cli.get_db_manager", side_effect=InvalidDBConnectionError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "init"])
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED


def test_cli_init_cmd_succeeds_when_schema_table_is_empty(runner, mocker, context):
    """Test fails if `esmigrate init` fails to check latest version for existing schemas"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    result = runner.invoke(cli.main, ["--profile", context.profile, "init"])
    assert result.exit_code == 0


def test_cli_init_cmd_succeeds_when_schema_exists(runner, mocker, context, success_schema):
    """Test fails if `esmigrate init` fails to check empty schema version table"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=success_schema)
    result = runner.invoke(cli.main, ["--profile", context.profile, "init"])
    assert result.exit_code == 0


@pytest.mark.parametrize("schema_version", ["invalid", "1.2.3", "1.x"])
def test_cli_upgrade_cmd_fails_with_value_error(runner, mocker, context, schema_version):
    """Test fails if `esmigrate upgrade` fails to check invalid schema version parameter"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", schema_version])
    assert result.exit_code == Errors.ERR_INVALID_SCMVER


def test_cli_upgrade_cmd_fails_with_db_connection_error(runner, mocker, context):
    """Test fails if `esmigrate upgrade` fails to check db connection error"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.cli.get_db_manager", side_effect=InvalidDBConnectionError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED


def test_cli_upgrade_cmd_fails_with_schema_db_error(runner, mocker, context, error_schema):
    """Test fails if `esmigrate upgrade` fails to check schema db error"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=error_schema)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE


def test_cli_upgrade_cmd_fails_with_invalid_directory_error(runner, mocker, context):
    """Test fails if `esmigrate upgrade` fails to check invalid schema directory"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", side_effect=NotADirectoryError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_DIRECTORY


def test_cli_upgrade_cmd_fails_with_invalid_schema_file_error(runner, mocker, context):
    """Test fails if `esmigrate upgrade` fails to check invalid schema files"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", side_effect=InvalidSchemaFileError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_FILE


def test_cli_upgrade_cmd_fails_with_invalid_command_error(runner, mocker, context, script_data):
    """Test fails if `esmigrate upgrade` fails to check command parser errors"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    mocker.patch("esmigrate.internals.db_manager.DBManager.insert_new_schema", return_value=None)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", return_value=[script_data])
    mocker.patch("esmigrate.internals.script_parser.ScriptParser.get_commands", side_effect=InvalidCommandScriptError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_COMMAND


def test_cli_upgrade_cmd_fails_with_elasticsearch_http_error(runner, mocker, context, script_data, http_error):
    """Test fails if `esmigrate upgrade` fails to check HTTP errors"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    mocker.patch("esmigrate.internals.db_manager.DBManager.insert_new_schema", return_value=None)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", return_value=[script_data])
    mocker.patch(
        "esmigrate.internals.script_parser.ScriptParser.get_commands",
        return_value=ScriptParser(context).get_commands(script_data.content),
    )
    mocker.patch("esmigrate.internals.http_handler.HTTPHandler.make_requests", side_effect=http_error)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == Errors.ERR_ES_HTTPERROR


def test_cli_upgrade_cmd_fails_with_elasticsearch_conn_error(runner, mocker, context, script_data):
    """Test fails if `esmigrate upgrade` fails to check connection errors"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", return_value=[script_data])
    mocker.patch(
        "esmigrate.internals.script_parser.ScriptParser.get_commands",
        return_value=ScriptParser(context).get_commands(script_data.content),
    )
    mocker.patch("esmigrate.internals.http_handler.HTTPHandler.make_requests", side_effect=ElasticsearchConnError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == Errors.ERR_ES_CONNERROR


def test_cli_upgrade_cmd_exits_for_empty_schema_directory(runner, mocker, context):
    """Test fails if `esmigrate upgrade` does not succeed when scan_dir returns empty list"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", return_value=[])
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == 0


def test_cli_upgrade_cmd_exits_when_requested_version_too_low(runner, mocker, context, script_data, success_schema):
    """Test fails if `esmigrate upgrade` does not exit early when requested version is already migrated"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=success_schema)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", return_value=[script_data])
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == 0


def test_cli_upgrade_cmd_fails_with_database_error(runner, mocker, context, script_data, http_response):
    """Test fails if `esmigrate upgrade` fails to check database errors during insert"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    mocker.patch("esmigrate.internals.db_manager.DBManager.insert_new_schema", side_effect=SchemaVersionSqlDbError)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", return_value=[script_data])
    mocker.patch(
        "esmigrate.internals.script_parser.ScriptParser.get_commands",
        return_value=ScriptParser(context).get_commands(script_data.content),
    )
    mocker.patch("esmigrate.internals.http_handler.HTTPHandler.make_requests", return_value=http_response)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE


def test_cli_upgrade_cmd_succeeds_for_valid_schema_file(runner, mocker, context, script_data, http_response):
    """Test fails if `esmigrate upgrade` does not succeed when scan_dir returns valid script data"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    mocker.patch("esmigrate.internals.db_manager.DBManager.insert_new_schema", return_value=None)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", return_value=[script_data])
    mocker.patch(
        "esmigrate.internals.script_parser.ScriptParser.get_commands",
        return_value=ScriptParser(context).get_commands(script_data.content),
    )
    mocker.patch("esmigrate.internals.http_handler.HTTPHandler.make_requests", return_value=http_response)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "latest"])
    assert result.exit_code == 0


def test_cli_rollback_cmd_fails_with_db_connection_error(runner, mocker, context):
    """Test fails if `esmigrate rollback` fails to check db connection error"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.cli.get_db_manager", side_effect=InvalidDBConnectionError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "rollback"])
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED


def test_cli_rollback_cmd_fails_with_sql_db_error(runner, mocker, context):
    """Test fails if `esmigrate rollback` fails to check sql query error"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.cli.get_db_manager", side_effect=SchemaVersionSqlDbError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "rollback"])
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE


def test_cli_rollback_cmd_succeeds_when_no_error_entry(runner, mocker, context):
    """Test fails if `esmigrate rollback` does not succeed when there is no error in schema db"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=None)
    result = runner.invoke(cli.main, ["--profile", context.profile, "rollback"])
    assert result.exit_code == 0


def test_cli_rollback_cmd_succeeds_with_error_entry(runner, mocker, context, error_schema):
    """Test fails if `esmigrate rollback` does not succeed when there are errors in schema db"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=error_schema)
    mocker.patch("esmigrate.internals.db_manager.DBManager.delete_all_failed_schema", return_value=None)
    result = runner.invoke(cli.main, ["--profile", context.profile, "rollback"])
    assert result.exit_code == 0


def test_cli_reset_cmd_fails_with_db_connection_error(runner, mocker, context):
    """Test fails if `esmigrate reset` fails to check db connection error"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.cli.get_db_manager", side_effect=InvalidDBConnectionError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "reset"])
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED


def test_cli_reset_cmd_fails_with_sql_db_error(runner, mocker, context):
    """Test fails if `esmigrate reset` fails to check sql query error"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.cli.get_db_manager", side_effect=SchemaVersionSqlDbError)
    result = runner.invoke(cli.main, ["--profile", context.profile, "reset"])
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE


def test_cli_reset_cmd_succeeds(runner, mocker, context):
    """Test fails if `esmigrate reset` does not exit without error"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.delete_all_schema", return_value=None)
    result = runner.invoke(cli.main, ["--profile", context.profile, "reset"])
    assert result.exit_code == 0


def make_script_data(version, sequence):
    return ScriptData(
        version, sequence, f"step_{version}_{sequence}", "exm", f"V{version}_{sequence}.exm", "GET twitter"
    )


def mock_upgrade_run(mocker, context, latest_schema, script_entries, http_response):
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    mocker.patch("esmigrate.internals.db_manager.DBManager.find_latest_schema", return_value=latest_schema)
    mocker.patch("esmigrate.internals.db_manager.DBManager.insert_new_schema", return_value=None)
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", return_value=script_entries)
    mocker.patch(
        "esmigrate.internals.script_parser.ScriptParser.get_commands",
        side_effect=lambda _: [Command("GET", "http://localhost:9200/twitter")],
    )
    mocker.patch("esmigrate.internals.http_handler.HTTPHandler.make_requests", return_value=http_response)


def test_cli_upgrade_cmd_applies_double_digit_sequence_after_single_digit(runner, mocker, context, http_response):
    """Test fails if `esmigrate upgrade` treats version 1.10 as older than an applied 1.9"""
    applied = SchemaVersion("1.9")
    applied.success = True
    applied.installed_rank = 1
    mock_upgrade_run(mocker, context, applied, [make_script_data(1, 9), make_script_data(1, 10)], http_response)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade"])
    assert result.exit_code == 0
    assert "Processing schema step_1_9.exm" not in result.output
    assert "Processing schema step_1_10.exm" in result.output
    assert "Schema database upgraded to 1.10" in result.output


def test_cli_upgrade_cmd_stops_at_double_digit_requested_version(runner, mocker, context, http_response):
    """Test fails if `esmigrate upgrade --schema-version 1.10` does not stop at 1.10"""
    entries = [make_script_data(1, 9), make_script_data(1, 10), make_script_data(1, 11)]
    mock_upgrade_run(mocker, context, None, entries, http_response)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "1.10"])
    assert result.exit_code == 0
    assert "Processing schema step_1_9.exm" in result.output
    assert "Processing schema step_1_10.exm" in result.output
    assert "Processing schema step_1_11.exm" not in result.output
    assert "Schema database upgraded to 1.10" in result.output


def test_cli_upgrade_cmd_treats_zero_version_as_explicit_target(runner, mocker, context, http_response):
    """Test fails if `esmigrate upgrade --schema-version 0` is treated as 'latest'"""
    mock_upgrade_run(mocker, context, None, [make_script_data(1, 0)], http_response)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "0"])
    assert result.exit_code == 0
    assert "Processing schema" not in result.output
