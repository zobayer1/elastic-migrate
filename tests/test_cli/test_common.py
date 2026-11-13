import pytest

from esmigrate import cli
from esmigrate.exceptions import Errors, InvalidConfigurationError
from tests.test_cli.helpers import (
    ES_HOST,
    create_legacy_table,
    create_v2_table,
    hold_lock,
    invoke,
    lock_rows,
    seed,
    stored_rows,
    write_schema,
)


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
