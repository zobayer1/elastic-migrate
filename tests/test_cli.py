# -*- coding: utf-8 -*-
import pytest
from click.testing import CliRunner
from requests import Response, HTTPError

from esmigrate import cli
from esmigrate.commons import ScriptData
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    Errors,
    InvalidDBConnectionError,
    InvalidSchemaFileError,
    InvalidCommandScriptError,
    SchemaVersionSqlDbError,
    ElasticsearchConnError,
)
from esmigrate.models import SchemaVersion
from esmigrate.internals import ScriptParser


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


def test_cli_upgrade_cmd_fails_with_value_error(runner, mocker, context):
    """Test fails if `esmigrate upgrade` fails to check invalid schema version parameter"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=context)
    result = runner.invoke(cli.main, ["--profile", context.profile, "upgrade", "--schema-version", "invalid"])
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
    mocker.patch("esmigrate.internals.glob_loader.GlobLoader.scan_dir", return_value=list())
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
