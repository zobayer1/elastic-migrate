import asyncio
import sqlite3

import httpx
import pytest
from click.testing import CliRunner
from sqlalchemy.ext.asyncio import AsyncEngine

from esmigrate import cli
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import Errors, InvalidConfigurationError, SchemaVersionSqlDbError
from esmigrate.internals import DBManager
from esmigrate.internals.db_manager import LEGACY_BACKUP_TABLE
from esmigrate.models import SchemaVersion

ES_HOST = "http://es.example.com:9200"

LEGACY_TABLE_DDL = (
    "CREATE TABLE esm_schema_version (version VARCHAR NOT NULL PRIMARY KEY, version_base INTEGER, "
    "version_rank INTEGER, installed_rank INTEGER UNIQUE, description VARCHAR, type VARCHAR, script VARCHAR, "
    "checksum BLOB, installed_by VARCHAR, installed_on DATETIME, execution_time INTEGER, success BOOLEAN, "
    "query_results VARCHAR)"
)


@pytest.fixture
def runner():
    """Pytest fixture for testing command line interfaces"""
    return CliRunner()


@pytest.fixture
def schema_dir(tmp_path):
    """Pytest fixture for providing an empty schema directory"""
    path = tmp_path / "schema_dir"
    path.mkdir()
    return path


@pytest.fixture
def context(tmp_path, schema_dir, mocker):
    """Pytest fixture for a loaded test profile backed by a temporary SQLite database and fake elasticsearch"""
    ctx = ContextConfig()
    ctx.profile = "test"
    ctx.es_host = ES_HOST
    ctx.schema_db = f"sqlite:///{tmp_path / 'esmigrate.db'}"
    ctx.schema_dir = str(schema_dir)
    mocker.patch("esmigrate.cli.ContextConfig.load_for", return_value=ctx)
    return ctx


def invoke(runner, *args):
    return runner.invoke(cli.main, ["--profile", "test", *args])


def write_schema(schema_dir, name, content="GET twitter"):
    (schema_dir / name).write_text(content)


def seed(context, *rows, namespace="default"):
    async def insert_rows():
        async with DBManager.connect(context.schema_db, namespace=namespace) as db:
            for version, success in rows:
                scmver = SchemaVersion(version)
                scmver.success = success
                await db.insert_new_schema(scmver)

    asyncio.run(insert_rows())


def stored_rows(context, namespace="default"):
    async def fetch_rows():
        async with DBManager.connect(context.schema_db, namespace=namespace) as db:
            return await db.find_all_schema()

    return asyncio.run(fetch_rows())


def test_cli_invocation_succeeds(runner):
    """Test fails if `esmigrate` does not print the banner and return with success"""
    result = runner.invoke(cli.main)
    assert result.exit_code == 0
    assert "Elasticsearch migrations made easy!" in result.output


def test_cli_with_help_argument_succeeds(runner):
    """Test fails if `esmigrate --help` does not return with success"""
    result = runner.invoke(cli.main, ["--help"])
    assert result.exit_code == 0
    assert "upgrade" in result.output


def test_cli_with_version_argument_succeeds(runner):
    """Test fails if `esmigrate --version` does not return with success"""
    result = runner.invoke(cli.main, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("v")


def test_cli_uses_default_profile_when_none_given(runner, context):
    """Test fails if commands without --profile do not load the `default` profile"""
    result = runner.invoke(cli.main, ["config"])
    assert result.exit_code == 0
    assert "Loading profile: default..." in result.output


def test_cli_help_shows_default_profile(runner):
    """Test fails if `esmigrate --help` does not document the default profile"""
    assert "[default: default]" in runner.invoke(cli.main, ["--help"]).output


def test_cli_config_command_fails_to_load_context_profile(runner):
    """Test fails if `esmigrate --profile {profile} {command}` does not return error"""
    result = runner.invoke(cli.main, ["--profile", "invalid-profile", "config"])
    assert result.exit_code == Errors.ERR_PROFILE_NOT_FOUND


def test_cli_fails_with_invalid_configuration(runner, mocker):
    """Test fails if an invalid profile field does not exit with the configuration error code"""
    mocker.patch("esmigrate.cli.ContextConfig.load_for", side_effect=InvalidConfigurationError("bad timeout"))
    result = invoke(runner, "config")
    assert result.exit_code == Errors.ERR_INVALID_CONFIGURATION
    assert "InvalidConfigurationError: bad timeout" in result.output


def test_cli_warns_when_certificate_verification_is_disabled(runner, context):
    """Test fails if disabling TLS verification does not print a warning on every run"""
    context.es_verify_certs = False
    result = invoke(runner, "config")
    assert result.exit_code == 0
    assert "WARNING: TLS certificate verification is disabled" in result.output


def test_cli_does_not_warn_when_certificates_are_verified(runner, context):
    """Test fails if the insecure warning is printed while verification is enabled"""
    assert "WARNING" not in invoke(runner, "config").output


def test_cli_config_command_loads_context_profile(runner, context):
    """Test fails if `esmigrate config` does not print the loaded profile"""
    result = invoke(runner, "config")
    assert result.exit_code == 0
    assert f"elastic_host: {ES_HOST}" in result.output


def test_cli_init_cmd_succeeds_when_schema_table_is_empty(runner, context):
    """Test fails if `esmigrate init` does not create an empty schema table"""
    result = invoke(runner, "init")
    assert result.exit_code == 0
    assert "Schema version database initialized" in result.output


def test_cli_init_cmd_succeeds_when_schema_exists(runner, context):
    """Test fails if `esmigrate init` does not report the latest installed version"""
    seed(context, ("1.0", True))
    result = invoke(runner, "init")
    assert result.exit_code == 0
    assert "already exists with latest version V1.0" in result.output


def test_cli_init_cmd_fails_with_db_error(runner, context):
    """Test fails if `esmigrate init` does not report an invalid database URL"""
    context.schema_db = "oracle://user@host/db"
    result = invoke(runner, "init")
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED


def create_legacy_table(context, rows=()):
    path = context.schema_db.removeprefix("sqlite:///")
    with sqlite3.connect(path) as conn:
        conn.execute(LEGACY_TABLE_DDL)
        for version, rank, success in rows:
            conn.execute(
                "INSERT INTO esm_schema_version (version, installed_rank, success, installed_on) VALUES (?, ?, ?, ?)",
                (version, rank, success, "2021-06-16 09:57:22"),
            )
    conn.close()


def test_cli_init_cmd_upgrades_legacy_table(runner, context):
    """Test fails if `esmigrate init` does not upgrade a v1 table and report the kept backup"""
    create_legacy_table(context, [("1.0", 1, 1)])
    result = invoke(runner, "init")
    assert result.exit_code == 0
    assert f"previous table kept as {LEGACY_BACKUP_TABLE}" in result.output
    assert "latest version V1.0" in result.output
    assert [row.version for row in stored_rows(context)] == ["1.0"]


def test_cli_init_cmd_fails_when_legacy_upgrade_fails(runner, context):
    """Test fails if `esmigrate init` does not report a failed v1 table upgrade"""
    create_legacy_table(context)
    path = context.schema_db.removeprefix("sqlite:///")
    with sqlite3.connect(path) as conn:
        conn.execute(f"CREATE TABLE {LEGACY_BACKUP_TABLE} (version VARCHAR)")
    conn.close()
    result = invoke(runner, "init")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE
    assert "already exists" in result.output


@pytest.mark.parametrize("command", [["upgrade"], ["rollback"], ["reset"]])
def test_cli_commands_refuse_legacy_table(runner, context, command):
    """Test fails if commands other than init run against a v1 table"""
    create_legacy_table(context, [("1.0", 1, 1)])
    result = invoke(runner, *command)
    assert result.exit_code == Errors.ERR_DB_LEGACY_TABLE
    assert "esmigrate init" in result.output


@pytest.mark.parametrize("schema_version", ["invalid", "1.2.3", "1.x"])
def test_cli_upgrade_cmd_fails_with_value_error(runner, context, schema_version):
    """Test fails if `esmigrate upgrade` fails to check invalid schema version parameter"""
    result = invoke(runner, "upgrade", "--schema-version", schema_version)
    assert result.exit_code == Errors.ERR_INVALID_SCMVER


@pytest.mark.parametrize("command", [["upgrade"], ["rollback"], ["reset"]])
def test_cli_commands_fail_with_db_connection_error(runner, context, command):
    """Test fails if commands do not report an invalid database URL"""
    context.schema_db = "oracle://user@host/db"
    result = invoke(runner, *command)
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED


def test_cli_upgrade_cmd_fails_with_schema_db_error(runner, context):
    """Test fails if `esmigrate upgrade` runs while the latest schema entry is failed"""
    seed(context, ("1.0", False))
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE
    assert "contains an error for version 1.0" in result.output


def test_cli_upgrade_cmd_fails_with_invalid_directory_error(runner, context, tmp_path):
    """Test fails if `esmigrate upgrade` does not report a missing schema directory"""
    context.schema_dir = str(tmp_path / "missing")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_DIRECTORY


def test_cli_upgrade_cmd_fails_with_invalid_schema_file_error(runner, context, schema_dir):
    """Test fails if `esmigrate upgrade` does not report schema files with illegal names"""
    write_schema(schema_dir, "V1_0_missing_double_underscore.exm")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_FILE


def test_cli_upgrade_cmd_exits_for_empty_schema_directory(runner, context):
    """Test fails if `esmigrate upgrade` does not exit cleanly for an empty schema directory"""
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "No schema file found" in result.output


def test_cli_upgrade_cmd_succeeds_for_valid_schema_file(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` does not run scripts in order and record host-relative results"""
    write_schema(schema_dir, "V1_0__create_twitter.exm", 'PUT twitter\n{"settings": {}}')
    write_schema(schema_dir, "V1_1__index_tweet.exm", 'PUT twitter/_doc/1\n{"user": "me"}')
    create = respx_mock.put(f"{ES_HOST}/twitter").respond(200, json={"acknowledged": True})
    index = respx_mock.put(f"{ES_HOST}/twitter/_doc/1").respond(201, json={"result": "created"})
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Schema database upgraded to 1.1" in result.output
    assert create.called
    assert index.called
    assert respx_mock.calls[0].request.url.path == "/twitter"
    rows = stored_rows(context)
    assert [(row.version, row.success, row.script) for row in rows] == [
        ("1.0", True, "V1_0__create_twitter.exm"),
        ("1.1", True, "V1_1__index_tweet.exm"),
    ]
    query_results = rows[0].query_results
    assert query_results is not None
    assert '"query": "PUT /twitter ' in query_results
    assert ES_HOST not in query_results


def test_cli_upgrade_cmd_exits_when_requested_version_too_low(runner, context, schema_dir):
    """Test fails if `esmigrate upgrade` does not exit early when requested version is already migrated"""
    seed(context, ("1.0", True))
    write_schema(schema_dir, "V1_0__create_twitter.exm")
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "nothing to do" in result.output


def test_cli_upgrade_cmd_fails_with_invalid_command_error(runner, context, schema_dir):
    """Test fails if `esmigrate upgrade` does not record a failed row for an invalid script"""
    write_schema(schema_dir, "V1_0__broken.exm", "PATCH twitter")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_COMMAND
    assert [(row.version, row.success) for row in stored_rows(context)] == [("1.0", False)]


def test_cli_upgrade_cmd_fails_with_elasticsearch_http_error(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` does not stop and record a failed row on an elasticsearch error response"""
    write_schema(schema_dir, "V1_0__create_twitter.exm", "PUT twitter\nPUT twitter/_doc/1")
    write_schema(schema_dir, "V1_1__never_runs.exm")
    respx_mock.put(f"{ES_HOST}/twitter").respond(400, json={"error": "resource_already_exists_exception"})
    second = respx_mock.put(f"{ES_HOST}/twitter/_doc/1").respond(200)
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_ES_HTTPERROR
    assert "400 Bad Request for PUT /twitter" in result.output
    assert not second.called
    rows = stored_rows(context)
    assert [(row.version, row.success) for row in rows] == [("1.0", False)]
    assert rows[0].query_results is not None
    assert "resource_already_exists_exception" in rows[0].query_results


def test_cli_upgrade_cmd_fails_with_elasticsearch_conn_error(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` records a row or does not report when elasticsearch is unreachable"""
    write_schema(schema_dir, "V1_0__create_twitter.exm")
    respx_mock.get(f"{ES_HOST}/twitter").mock(side_effect=httpx.ConnectError("refused"))
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_ES_CONNERROR
    assert stored_rows(context) == []


def test_cli_upgrade_cmd_fails_with_unusable_certificates(runner, context, schema_dir, tmp_path):
    """Test fails if an unreadable CA bundle is not reported as a configuration error before any request"""
    write_schema(schema_dir, "V1_0__create_twitter.exm")
    (tmp_path / "ca.pem").write_text("not a certificate")
    context.es_ca_certs = str(tmp_path / "ca.pem")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_CONFIGURATION
    assert "Cannot load TLS certificates" in result.output
    assert stored_rows(context) == []


def test_cli_upgrade_cmd_fails_with_database_error(runner, context, schema_dir, respx_mock, mocker):
    """Test fails if `esmigrate upgrade` does not report database errors during insert"""
    write_schema(schema_dir, "V1_0__create_twitter.exm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    mocker.patch("esmigrate.internals.DBManager.insert_new_schema", side_effect=SchemaVersionSqlDbError("locked"))
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE
    assert "SchemaVersionSqlDbError: locked" in result.output


def test_cli_upgrade_cmd_closes_client_and_engine_on_failure(runner, context, schema_dir, respx_mock, mocker):
    """Test fails if the HTTP client or database engine stays open after a failed upgrade"""
    write_schema(schema_dir, "V1_0__create_twitter.exm")
    respx_mock.get(f"{ES_HOST}/twitter").mock(side_effect=httpx.ConnectError("refused"))
    aclose = mocker.spy(httpx.AsyncClient, "aclose")
    dispose = mocker.spy(AsyncEngine, "dispose")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_ES_CONNERROR
    assert aclose.call_count == 1
    assert dispose.call_count == 1


def test_cli_upgrade_cmd_applies_double_digit_sequence_after_single_digit(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` treats version 1.10 as older than an applied 1.9"""
    seed(context, ("1.9", True))
    write_schema(schema_dir, "V1_9__step_1_9.exm")
    write_schema(schema_dir, "V1_10__step_1_10.exm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Processing schema step_1_9.exm" not in result.output
    assert "Processing schema step_1_10.exm" in result.output
    assert "Schema database upgraded to 1.10" in result.output


def test_cli_upgrade_cmd_stops_at_double_digit_requested_version(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade --schema-version 1.10` does not stop at 1.10"""
    for sequence in (9, 10, 11):
        write_schema(schema_dir, f"V1_{sequence}__step_1_{sequence}.exm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade", "--schema-version", "1.10")
    assert result.exit_code == 0
    assert "Processing schema step_1_9.exm" in result.output
    assert "Processing schema step_1_10.exm" in result.output
    assert "Processing schema step_1_11.exm" not in result.output
    assert "Schema database upgraded to 1.10" in result.output


def test_cli_upgrade_cmd_treats_zero_version_as_explicit_target(runner, context, schema_dir):
    """Test fails if `esmigrate upgrade --schema-version 0` is treated as 'latest'"""
    write_schema(schema_dir, "V1_0__create_twitter.exm")
    result = invoke(runner, "upgrade", "--schema-version", "0")
    assert result.exit_code == 0
    assert "Processing schema" not in result.output


def test_cli_upgrade_cmd_uses_profile_namespace(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` ignores the profile schema namespace"""
    seed(context, ("1.0", True))
    context.schema_namespace = "billing"
    write_schema(schema_dir, "V1_0__create_twitter.exm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Processing schema create_twitter.exm" in result.output
    assert [row.version for row in stored_rows(context, namespace="billing")] == ["1.0"]
    assert [row.version for row in stored_rows(context)] == ["1.0"]


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
    assert [row.version for row in stored_rows(context)] == ["1.0"]


def test_cli_rollback_cmd_fails_with_sql_db_error(runner, context, mocker):
    """Test fails if `esmigrate rollback` fails to check sql query error"""
    seed(context, ("1.0", False))
    mocker.patch("esmigrate.internals.DBManager.delete_all_failed_schema", side_effect=SchemaVersionSqlDbError)
    result = invoke(runner, "rollback")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE


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
