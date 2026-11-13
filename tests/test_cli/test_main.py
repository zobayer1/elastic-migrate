from unittest.mock import AsyncMock

import httpx
import pytest

from esmigrate import cli
from esmigrate.exceptions import Errors, InvalidConfigurationError, SchemaVersionSqlDbError
from esmigrate.internals import LEGACY_TABLE
from tests.test_cli.helpers import (
    ES_HOST,
    create_legacy_table,
    create_v2_table,
    history_rows,
    hold_lock,
    invoke,
    lock_rows,
    raw_rows,
    seed,
    stored_rows,
    versions,
    write_schema,
)


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


def test_cli_writes_status_to_stderr_and_data_to_stdout(runner, context):
    """Test fails if status messages pollute stdout or the config output leaves stdout"""
    result = invoke(runner, "config")
    assert result.exit_code == 0
    assert "Configurations:" in result.stdout
    assert "Loading profile" not in result.stdout
    assert "Loading profile: test..." in result.stderr


def test_cli_does_not_duplicate_log_lines_across_invocations(runner, context):
    """Test fails if repeated invocations in one process print each status line more than once"""
    invoke(runner, "config")
    assert invoke(runner, "config").stderr.count("Loading profile") == 1


def test_cli_rejects_verbose_with_quiet(runner, context):
    """Test fails if --verbose and --quiet are accepted together"""
    result = runner.invoke(cli.main, ["-v", "-q", "--profile", "test", "config"])
    assert result.exit_code == 2
    assert "cannot be used together" in result.output


def test_cli_verbose_logs_each_request(runner, context, schema_dir, respx_mock):
    """Test fails if --verbose does not log verb, path, sizes, status and duration without the request body"""
    write_schema(schema_dir, "V1_0__create_twitter.esm", 'PUT twitter\n{"secret": "do-not-log"}')
    respx_mock.put(f"{ES_HOST}/twitter").respond(200, json={"acknowledged": True})
    verbose = runner.invoke(cli.main, ["--verbose", "--profile", "test", "upgrade"])
    assert verbose.exit_code == 0, verbose.output
    assert "PUT /twitter (" in verbose.stderr
    assert "-> 200 (" in verbose.stderr
    assert " ms" in verbose.stderr
    assert "do-not-log" not in verbose.output
    write_schema(schema_dir, "V1_1__read_twitter.esm", "GET twitter")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    default = invoke(runner, "upgrade")
    assert "Processing schema read_twitter.esm" in default.output
    assert "-> 200" not in default.output


def test_cli_quiet_shows_only_errors(runner, context, schema_dir, respx_mock):
    """Test fails if --quiet prints status messages or hides errors"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    respx_mock.get(f"{ES_HOST}/twitter").mock(side_effect=httpx.ConnectError("refused"))
    result = runner.invoke(cli.main, ["--quiet", "--profile", "test", "upgrade"])
    assert result.exit_code == Errors.ERR_ES_CONNERROR
    assert "Processing schema" not in result.output
    assert "Loading profile" not in result.output
    assert "ERROR: ElasticsearchConnError: ConnectError: refused" in result.output


def test_cli_log_file_records_audit_trail(runner, context, schema_dir, respx_mock, tmp_path):
    """Test fails if --log-file does not record run start, scripts, requests and exit code even with --quiet"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    log_file = tmp_path / "esmigrate.log"
    result = runner.invoke(cli.main, ["-q", "--log-file", str(log_file), "--profile", "test", "upgrade"])
    assert result.exit_code == 0, result.output
    text = log_file.read_text()
    assert "upgrade: profile=test namespace=default" in text
    assert "Schema 1.0 up: script=V1_0__create_twitter.esm checksum=" in text
    assert "GET /twitter (0 bytes) -> 200" in text
    assert "Schema 1.0 up succeeded in" in text
    assert "Finished upgrade with exit code 0" in text


def test_cli_uses_profile_log_file_unless_overridden(runner, context, tmp_path):
    """Test fails if the profile log_file is ignored or --log-file does not override it"""
    context.log_file = str(tmp_path / "profile.log")
    invoke(runner, "config")
    assert "config: profile=test" in (tmp_path / "profile.log").read_text()
    runner.invoke(cli.main, ["--log-file", str(tmp_path / "flag.log"), "--profile", "test", "config"])
    assert "config: profile=test" in (tmp_path / "flag.log").read_text()
    assert (tmp_path / "profile.log").read_text().count("config: profile=test") == 1


def test_cli_does_not_leak_log_file_into_next_invocation(runner, context, tmp_path):
    """Test fails if a log file from one invocation keeps receiving records from the next"""
    runner.invoke(cli.main, ["--log-file", str(tmp_path / "first.log"), "--profile", "test", "config"])
    invoke(runner, "config")
    assert (tmp_path / "first.log").read_text().count("Profile loaded") == 1


@pytest.mark.parametrize("source", ["flag", "profile"])
def test_cli_reports_unwritable_log_file(runner, context, tmp_path, source):
    """Test fails if a log file in a missing directory is not reported with the configuration exit code"""
    path = str(tmp_path / "missing" / "esmigrate.log")
    args = ["--log-file", path] if source == "flag" else []
    if source == "profile":
        context.log_file = path
    result = runner.invoke(cli.main, [*args, "--profile", "test", "config"])
    assert result.exit_code == Errors.ERR_INVALID_CONFIGURATION
    assert "Cannot open log file" in result.output


def test_cli_passes_schema_to_database(runner, context, tmp_path):
    """Test fails if commands do not use schema_db_schema or the audit log omits it"""
    context.schema_db_schema = "main"
    result = runner.invoke(cli.main, ["--log-file", str(tmp_path / "esmigrate.log"), "--profile", "test", "init"])
    assert result.exit_code == 0, result.output
    assert "schema_db_schema=main" in (tmp_path / "esmigrate.log").read_text()
    context.schema_db_schema = "missing_schema"
    result = invoke(runner, "init")
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED
    assert "Database schema missing_schema does not exist" in result.output


def test_cli_audit_masks_database_password(runner, context, tmp_path):
    """Test fails if the audit log records the schema database password"""
    context.schema_db = "postgresql://migrator:s3cr3t@db.example.com/esmigrate"
    runner.invoke(cli.main, ["--log-file", str(tmp_path / "esmigrate.log"), "--profile", "test", "config"])
    text = (tmp_path / "esmigrate.log").read_text()
    assert "s3cr3t" not in text
    assert "schema_db=postgresql://migrator:***@db.example.com/esmigrate" in text


@pytest.mark.parametrize("command", ["init", "config", "upgrade", "rollback", "reset", "unlock"])
def test_cli_subcommand_help_works_without_profile(runner, command):
    """Test fails if `esmigrate <command> --help` needs a loadable profile"""
    result = runner.invoke(cli.main, ["--profile", "no-such-profile", command, "--help"])
    assert result.exit_code == 0, result.output
    assert f"Usage: main {command} [OPTIONS]" in result.output
    assert "Loading profile" not in result.output


def test_cli_config_command_fails_to_load_context_profile(runner):
    """Test fails if `esmigrate --profile {profile} {command}` does not return error"""
    result = runner.invoke(cli.main, ["--profile", "invalid-profile", "config"])
    assert result.exit_code == Errors.ERR_PROFILE_NOT_FOUND


def test_cli_fails_with_invalid_configuration(runner, mocker):
    """Test fails if an invalid profile field does not exit with the configuration error code"""
    mocker.patch("esmigrate.contexts.ContextConfig.load_for", side_effect=InvalidConfigurationError("bad timeout"))
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


@pytest.mark.parametrize(("create", "layout"), [(create_legacy_table, "V1"), (create_v2_table, "V2")])
def test_cli_init_cmd_copies_old_table(runner, context, create, layout):
    """Test fails if `esmigrate init` does not copy a v1 or v2 table and report the layout and the kept table"""
    if layout == "V1":
        create(context, [("1.0", 1, 1)])
    else:
        create(context, [("default", "1.0", 1, 1)])
    result = invoke(runner, "init")
    assert result.exit_code == 0, result.output
    assert f"Copied {layout} schema versions, previous table kept as {LEGACY_TABLE}" in result.output
    assert "latest version V1.0" in result.output
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


@pytest.mark.parametrize("command", [["upgrade"], ["rollback"], ["reset"]])
@pytest.mark.parametrize(("create", "layout"), [(create_legacy_table, "V1"), (create_v2_table, "V2")])
def test_cli_commands_refuse_old_tables(runner, context, command, create, layout):
    """Test fails if commands other than init run against a v1 or v2 table"""
    if layout == "V1":
        create(context, [("1.0", 1, 1)])
    else:
        create(context, [("default", "1.0", 1, 1)])
    result = invoke(runner, *command)
    assert result.exit_code == Errors.ERR_DB_LEGACY_TABLE
    assert f"Schema tables use the {layout} layout, run `esmigrate init` to upgrade" in result.output


@pytest.mark.parametrize("command", [["upgrade"], ["rollback"], ["reset"]])
def test_cli_commands_fail_with_db_connection_error(runner, context, command):
    """Test fails if commands do not report an invalid database URL"""
    context.schema_db = "oracle://user@host/db"
    result = invoke(runner, *command)
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED


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


@pytest.mark.parametrize("command", ["upgrade", "rollback", "reset"])
def test_cli_commands_fail_when_migration_lock_is_held(runner, context, schema_dir, command):
    """Test fails if a command runs while another esmigrate run holds the namespace lock"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    seed(context, ("1.0", False))
    hold_lock(context)
    result = invoke(runner, command)
    assert result.exit_code == Errors.ERR_DB_LOCKED
    assert "MigrationLockedError: Migration lock is held by other-host pid 4242 since" in result.output
    assert [(str(row.version), row.success) for row in stored_rows(context)] == [("1.0", False)]


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_cli_upgrade_releases_lock(runner, context, schema_dir, respx_mock, outcome):
    """Test fails if the migration lock is left behind after a successful or failed upgrade"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200 if outcome == "success" else 500)
    result = invoke(runner, "upgrade")
    assert result.exit_code == (0 if outcome == "success" else Errors.ERR_ES_HTTPERROR)
    assert lock_rows(context) == []


def test_cli_logs_lock_lifecycle(runner, context, tmp_path):
    """Test fails if acquiring and releasing the lock, with the timeout, are not recorded in the audit log"""
    context.lock_timeout = 2.5
    runner.invoke(cli.main, ["--log-file", str(tmp_path / "esmigrate.log"), "--profile", "test", "reset"])
    text = (tmp_path / "esmigrate.log").read_text()
    assert "Acquiring migration lock for namespace default (timeout 2.5s)" in text
    assert "Migration lock acquired" in text
    assert "Migration lock released after" in text


def test_cli_unlock_with_yes_removes_stuck_lock(runner, context):
    """Test fails if unlock --yes does not remove a stuck SQLite lock"""
    hold_lock(context)
    result = invoke(runner, "unlock", "--yes")
    assert result.exit_code == 0
    assert "Removed the migration lock for namespace default" in result.output
    assert lock_rows(context) == []


@pytest.mark.parametrize(("answer", "remaining"), [("y\n", 0), ("n\n", 1)])
def test_cli_unlock_asks_for_confirmation(runner, context, answer, remaining):
    """Test fails if unlock does not confirm first, or removes the lock when the answer is no"""
    hold_lock(context)
    result = runner.invoke(cli.main, ["--profile", "test", "unlock"], input=answer)
    assert result.exit_code == 0
    assert "Remove the migration lock for namespace default?" in result.output
    assert len(lock_rows(context)) == remaining
    if remaining:
        assert "Unlock cancelled" in result.output


def test_cli_unlock_reports_when_no_lock_is_held(runner, context):
    """Test fails if unlock without a stuck lock does not say so"""
    result = invoke(runner, "unlock", "--yes")
    assert result.exit_code == 0
    assert "No migration lock is held for namespace default" in result.output


def test_cli_unlock_explains_server_database_locks(runner, context, mocker):
    """Test fails if unlock on PostgreSQL or MySQL does not explain that locks release automatically"""
    mocker.patch("esmigrate.internals.DBManager.force_unlock", AsyncMock(return_value=None))
    result = invoke(runner, "unlock", "--yes")
    assert result.exit_code == 0
    assert "released automatically when the holder exits" in result.output


def test_cli_unlock_reports_database_errors(runner, context):
    """Test fails if unlock does not report an invalid database URL"""
    context.schema_db = "oracle://user@host/db"
    assert invoke(runner, "unlock", "--yes").exit_code == Errors.ERR_DB_CONNECTION_FAILED


def test_cli_init_cmd_prints_sql_without_connecting(runner, context, tmp_path):
    """Test fails if `esmigrate init --print-sql` does not print only the SQL to stdout without opening the database"""
    result = invoke(runner, "init", "--print-sql")
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("CREATE TABLE esm_schema_state (")
    assert "CREATE TABLE esm_schema_history (" in result.stdout
    assert "CREATE INDEX ix_esm_schema_history_namespace_id ON esm_schema_history (namespace, id);" in result.stdout
    assert "Loading profile: test..." in result.stderr
    assert "Loading profile" not in result.stdout
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
    assert "InvalidDBConnectionError: Unsupported database: oracle" in result.stderr
    assert result.stdout == ""


def test_cli_init_cmd_help_documents_print_sql(runner):
    """Test fails if `esmigrate init --help` does not describe the copy and the --print-sql option"""
    result = runner.invoke(cli.main, ["init", "--help"])
    assert result.exit_code == 0
    assert "copying rows from v1 and v2 tables" in result.stdout
    assert "--print-sql" in result.stdout
