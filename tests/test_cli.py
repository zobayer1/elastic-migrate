import asyncio
import json
import sqlite3
import ssl
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from click.testing import CliRunner
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from esmigrate import cli
from esmigrate.commons import Direction, Migration, MigVersion, ScriptData
from esmigrate.commons.script_data import make_sha1
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import Errors, InvalidConfigurationError, SchemaVersionSqlDbError
from esmigrate.internals import LEGACY_TABLE, DBManager
from esmigrate.internals.migration_lock import LOCK_TABLE

ES_HOST = "http://es.example.com:9200"

LEGACY_TABLE_DDL = (
    "CREATE TABLE esm_schema_version (version VARCHAR NOT NULL PRIMARY KEY, version_base INTEGER, "
    "version_rank INTEGER, installed_rank INTEGER UNIQUE, description VARCHAR, type VARCHAR, script VARCHAR, "
    "checksum BLOB, installed_by VARCHAR, installed_on DATETIME, execution_time INTEGER, success BOOLEAN, "
    "query_results VARCHAR)"
)

V2_TABLE_DDL = (
    "CREATE TABLE esm_schema_version (namespace VARCHAR NOT NULL, version VARCHAR NOT NULL, version_base INTEGER, "
    "version_rank INTEGER, installed_rank INTEGER, description VARCHAR, type VARCHAR, script VARCHAR, "
    "checksum BLOB, installed_by VARCHAR, installed_on DATETIME, execution_time INTEGER, success BOOLEAN, "
    "query_results VARCHAR, PRIMARY KEY (namespace, version))"
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
    async def record_rows():
        async with DBManager.connect(context.schema_db, namespace=namespace) as db:
            for text, success in rows:
                version = MigVersion.parse(text)
                path = f"V{version.base}_{version.rank}__seeded.esm"
                run = await db.start_run(Direction.UP, Migration(up=ScriptData(version, "seeded", "esm", path, "")))
                if success is not None:
                    await db.finish_run(run, success, 1, "")

    asyncio.run(record_rows())


def stored_rows(context, namespace="default"):
    async def fetch_rows():
        async with DBManager.connect(context.schema_db, namespace=namespace) as db:
            return await db.find_all_schema()

    return asyncio.run(fetch_rows())


def versions(context, namespace="default"):
    return [str(row.version) for row in stored_rows(context, namespace)]


def history_rows(context, namespace="default"):
    async def fetch_rows():
        async with DBManager.connect(context.schema_db, namespace=namespace) as db:
            return await db.find_history()

    return asyncio.run(fetch_rows())


def raw_rows(context, sql):
    path = context.schema_db.removeprefix("sqlite:///")
    with sqlite3.connect(path) as conn:
        rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


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


def create_v2_table(context, rows=()):
    path = context.schema_db.removeprefix("sqlite:///")
    with sqlite3.connect(path) as conn:
        conn.execute(V2_TABLE_DDL)
        for namespace, version, rank, success in rows:
            conn.execute(
                "INSERT INTO esm_schema_version (namespace, version, installed_rank, success, execution_time) "
                "VALUES (?, ?, ?, ?, 2)",
                (namespace, version, rank, success),
            )
    conn.close()


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


@pytest.mark.parametrize("schema_version", ["invalid", "1.2.3", "1.x", "2147483648", "1.2147483648"])
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


@pytest.mark.parametrize(("success", "state"), [(False, "failed"), (None, "was interrupted")])
def test_cli_upgrade_cmd_refuses_failed_or_interrupted_row(runner, context, schema_dir, respx_mock, success, state):
    """Test fails if `esmigrate upgrade` runs, or does not name the state and next steps, after a bad latest row"""
    seed(context, ("1.0", success))
    write_schema(schema_dir, "V1_1__next.esm")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE
    assert (
        f"ERROR: SchemaVersionSqlDbError: Version 1.0 {state}, "
        "see `esmigrate status` and resolve it with `esmigrate force`"
    ) in result.output
    assert len(respx_mock.calls) == 0


def test_cli_upgrade_cmd_fails_with_invalid_directory_error(runner, context, tmp_path):
    """Test fails if `esmigrate upgrade` does not report a missing schema directory"""
    context.schema_dir = str(tmp_path / "missing")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_DIRECTORY


def test_cli_upgrade_cmd_fails_with_invalid_schema_file_error(runner, context, schema_dir):
    """Test fails if `esmigrate upgrade` does not report schema files with illegal names"""
    write_schema(schema_dir, "V1_0_missing_double_underscore.esm")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_FILE


def test_cli_upgrade_cmd_exits_for_empty_schema_directory(runner, context):
    """Test fails if `esmigrate upgrade` does not exit cleanly for an empty schema directory"""
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "No schema file found" in result.output


def test_cli_upgrade_cmd_succeeds_for_valid_schema_file(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` does not run scripts in order and record host-relative results"""
    write_schema(schema_dir, "V1_0__create_twitter.esm", 'PUT twitter\n{"settings": {}}')
    write_schema(schema_dir, "V1_1__index_tweet.esm", 'PUT twitter/_doc/1\n{"user": "me"}')
    create = respx_mock.put(f"{ES_HOST}/twitter").respond(200, json={"acknowledged": True})
    index = respx_mock.put(f"{ES_HOST}/twitter/_doc/1").respond(201, json={"result": "created"})
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Schema database upgraded to 1.1" in result.output
    assert create.called
    assert index.called
    assert respx_mock.calls[0].request.url.path == "/twitter"
    rows = stored_rows(context)
    assert [(str(row.version), row.success, row.script) for row in rows] == [
        ("1.0", True, "V1_0__create_twitter.esm"),
        ("1.1", True, "V1_1__index_tweet.esm"),
    ]
    query_results = rows[0].query_results
    assert query_results is not None
    assert '"query": "PUT /twitter ' in query_results
    assert ES_HOST not in query_results


def test_cli_upgrade_cmd_reports_up_to_date_database(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` without a target does not report an up-to-date database and stop"""
    seed(context, ("1.0", True))
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Schema database is up to date at version 1.0, nothing to do" in result.output
    assert "requested" not in result.output
    assert len(respx_mock.calls) == 0


@pytest.mark.parametrize(
    ("applied", "files", "target", "expected"),
    [
        (["1.0", "2.0"], ["V1_0__first.esm", "V2_0__second.esm", "V3_0__third.esm"], "1.0", "1.0 (database at 2.0)"),
        (["1.0"], ["V1_0__first.esm", "V2_0__second.esm"], "1.5", "1.5 (database at 1.0)"),
    ],
)
def test_cli_upgrade_cmd_reports_nothing_to_apply_up_to_target(
    runner, context, schema_dir, respx_mock, applied, files, target, expected
):
    """Test fails if a target at or below the database version, or with no file in range, is not reported as such"""
    seed(context, *[(version, True) for version in applied])
    for name in files:
        write_schema(schema_dir, name)
    result = invoke(runner, "upgrade", "--schema-version", target)
    assert result.exit_code == 0
    assert f"No migrations to apply up to version {expected}, nothing to do" in result.output
    assert "up to date" not in result.output
    assert len(respx_mock.calls) == 0
    assert versions(context) == applied


def test_cli_upgrade_cmd_fails_with_invalid_command_error(runner, context, schema_dir, respx_mock):
    """Test fails if an invalid script sends a request or records anything"""
    write_schema(schema_dir, "V1_0__broken.esm", "PATCH twitter")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_COMMAND
    assert len(respx_mock.calls) == 0
    assert stored_rows(context) == []
    assert history_rows(context) == []


def test_cli_upgrade_cmd_fails_with_elasticsearch_http_error(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` does not stop and record a failed row on an elasticsearch error response"""
    write_schema(schema_dir, "V1_0__create_twitter.esm", "PUT twitter\nPUT twitter/_doc/1")
    write_schema(schema_dir, "V1_1__never_runs.esm")
    respx_mock.put(f"{ES_HOST}/twitter").respond(400, json={"error": "resource_already_exists_exception"})
    second = respx_mock.put(f"{ES_HOST}/twitter/_doc/1").respond(200)
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_ES_HTTPERROR
    assert "400 Bad Request for PUT /twitter" in result.output
    assert not second.called
    rows = stored_rows(context)
    assert [(str(row.version), row.success) for row in rows] == [("1.0", False)]
    assert rows[0].query_results is not None
    assert "resource_already_exists_exception" in rows[0].query_results


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("slow"),
        ssl.SSLError(1, "[SSL: TLSV13_ALERT_CERTIFICATE_REQUIRED] tlsv13 alert certificate required"),
    ],
)
def test_cli_upgrade_cmd_undoes_a_script_that_never_reached_elasticsearch(
    runner, context, schema_dir, respx_mock, error
):
    """Test fails if a first request that never reached elasticsearch leaves a state row or loses its history"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    respx_mock.get(f"{ES_HOST}/twitter").mock(side_effect=error)
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_ES_CONNERROR
    assert stored_rows(context) == []
    (entry,) = history_rows(context)
    assert entry.success is False
    assert entry.query_results is not None
    stored = json.loads(entry.query_results)
    assert stored["query"] == "GET /twitter None"
    assert stored["status"] is None
    assert stored["result"].startswith("ElasticsearchConnError: ")
    respx_mock.get(f"{ES_HOST}/twitter").mock(side_effect=None, return_value=httpx.Response(200))
    assert invoke(runner, "upgrade").exit_code == 0
    assert [(str(row.version), row.success) for row in stored_rows(context)] == [("1.0", True)]


def test_cli_upgrade_cmd_fails_with_unusable_certificates(runner, context, schema_dir, tmp_path):
    """Test fails if an unreadable CA bundle is not reported as a configuration error before any request"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    (tmp_path / "ca.pem").write_text("not a certificate")
    context.es_ca_certs = str(tmp_path / "ca.pem")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_CONFIGURATION
    assert "Cannot load TLS certificates" in result.output
    assert stored_rows(context) == []


def test_cli_upgrade_cmd_leaves_run_interrupted_when_result_write_fails(
    runner, context, schema_dir, respx_mock, mocker
):
    """Test fails if a failed result write is not reported with exit 21 and the run left as interrupted"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    mocker.patch("esmigrate.internals.DBManager.finish_run", side_effect=SchemaVersionSqlDbError("locked"))
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE
    assert "SchemaVersionSqlDbError: locked" in result.output
    assert [(str(row.version), row.success) for row in stored_rows(context)] == [("1.0", None)]


def test_cli_upgrade_cmd_sends_nothing_when_start_cannot_be_recorded(runner, context, schema_dir, respx_mock, mocker):
    """Test fails if a script runs although its start could not be recorded"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    mocker.patch("esmigrate.internals.DBManager.start_run", side_effect=SchemaVersionSqlDbError("locked"))
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE
    assert len(respx_mock.calls) == 0


def test_cli_upgrade_cmd_closes_client_and_engine_on_failure(runner, context, schema_dir, respx_mock, mocker):
    """Test fails if the HTTP client or database engine stays open after a failed upgrade"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
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
    write_schema(schema_dir, "V1_9__step_1_9.esm")
    write_schema(schema_dir, "V1_10__step_1_10.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Processing schema step_1_9.esm" not in result.output
    assert "Processing schema step_1_10.esm" in result.output
    assert "Schema database upgraded to 1.10" in result.output


def test_cli_upgrade_cmd_stops_at_double_digit_requested_version(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade --schema-version 1.10` does not stop at 1.10"""
    for sequence in (9, 10, 11):
        write_schema(schema_dir, f"V1_{sequence}__step_1_{sequence}.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade", "--schema-version", "1.10")
    assert result.exit_code == 0
    assert "Processing schema step_1_9.esm" in result.output
    assert "Processing schema step_1_10.esm" in result.output
    assert "Processing schema step_1_11.esm" not in result.output
    assert "Schema database upgraded to 1.10" in result.output


def test_cli_upgrade_cmd_treats_zero_version_as_explicit_target(runner, context, schema_dir):
    """Test fails if `esmigrate upgrade --schema-version 0` is treated as 'latest'"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    result = invoke(runner, "upgrade", "--schema-version", "0")
    assert result.exit_code == 0
    assert "Processing schema" not in result.output
    assert "No migrations to apply up to version 0.0 (database at 0.0), nothing to do" in result.output


def test_cli_upgrade_cmd_uses_profile_namespace(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` ignores the profile schema namespace"""
    seed(context, ("1.0", True))
    context.schema_namespace = "billing"
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Processing schema create_twitter.esm" in result.output
    assert [str(row.version) for row in stored_rows(context, namespace="billing")] == ["1.0"]
    assert [str(row.version) for row in stored_rows(context)] == ["1.0"]


def test_cli_upgrade_cmd_runs_up_and_plain_scripts_only(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` runs a down script or does not record the up and plain scripts"""
    up_script = 'PUT twitter\n{"settings": {}}'
    write_schema(schema_dir, "V1_0__create_twitter.up.esm", up_script)
    write_schema(schema_dir, "V1_0__create_twitter.down.esm", "DELETE twitter")
    write_schema(schema_dir, "V1_1__create_tweets.esm", 'PUT tweets\n{"settings": {}}')
    respx_mock.put(f"{ES_HOST}/twitter").respond(200, json={"acknowledged": True})
    respx_mock.put(f"{ES_HOST}/tweets").respond(200, json={"acknowledged": True})
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Schema database upgraded to 1.1" in result.output
    assert len(respx_mock.calls) == 2
    rows = stored_rows(context)
    assert [(str(row.version), row.success, row.script, row.description) for row in rows] == [
        ("1.0", True, "V1_0__create_twitter.up.esm", "create_twitter.esm"),
        ("1.1", True, "V1_1__create_tweets.esm", "create_tweets.esm"),
    ]
    assert rows[0].checksum == make_sha1(up_script)


def test_cli_upgrade_cmd_records_down_only_migration_without_requests(runner, context, schema_dir, respx_mock):
    """Test fails if a down-only migration sends a request, is not recorded or is not logged as having no up script"""
    write_schema(schema_dir, "V1_0__drop_old_index.down.esm", "DELETE old_index")
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Schema 1.0 has no up script, recording it without requests" in result.output
    assert len(respx_mock.calls) == 0
    rows = stored_rows(context)
    assert [(str(row.version), row.version_base, row.version_rank, row.description, row.success) for row in rows] == [
        ("1.0", 1, 0, "drop_old_index.esm", True),
    ]
    assert rows[0].script is None
    assert rows[0].checksum is None
    assert rows[0].query_results == ""


def test_cli_upgrade_cmd_does_not_repeat_down_only_migration(runner, context, schema_dir, respx_mock):
    """Test fails if a recorded down-only migration is processed again by a later upgrade"""
    write_schema(schema_dir, "V1_0__drop_old_index.down.esm", "DELETE old_index")
    assert invoke(runner, "upgrade").exit_code == 0
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Processing schema" not in result.output
    assert len(stored_rows(context)) == 1


def test_cli_upgrade_cmd_applies_down_only_migration_between_others(runner, context, schema_dir, respx_mock):
    """Test fails if a down-only migration interrupts the scripts before and after it"""
    write_schema(schema_dir, "V1_0__first.esm", 'PUT first\n{"settings": {}}')
    write_schema(schema_dir, "V1_1__second.down.esm", "DELETE second")
    write_schema(schema_dir, "V1_2__third.up.esm", 'PUT third\n{"settings": {}}')
    respx_mock.put(f"{ES_HOST}/first").respond(200, json={"acknowledged": True})
    respx_mock.put(f"{ES_HOST}/third").respond(200, json={"acknowledged": True})
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert len(respx_mock.calls) == 2
    assert [(str(row.version), row.script) for row in stored_rows(context)] == [
        ("1.0", "V1_0__first.esm"),
        ("1.1", None),
        ("1.2", "V1_2__third.up.esm"),
    ]


def test_cli_upgrade_cmd_stops_at_requested_down_only_migration(runner, context, schema_dir, respx_mock):
    """Test fails if a requested version that is down-only is not the last one applied"""
    write_schema(schema_dir, "V1_0__first.esm", 'PUT first\n{"settings": {}}')
    write_schema(schema_dir, "V1_1__second.down.esm", "DELETE second")
    write_schema(schema_dir, "V1_2__third.esm", 'PUT third\n{"settings": {}}')
    respx_mock.put(f"{ES_HOST}/first").respond(200, json={"acknowledged": True})
    result = invoke(runner, "upgrade", "--schema-version", "1.1")
    assert result.exit_code == 0
    assert "Schema database upgraded to 1.1" in result.output
    assert [str(row.version) for row in stored_rows(context)] == ["1.0", "1.1"]


@pytest.mark.parametrize("down_script", ["THIS IS NOT A COMMAND", ""])
def test_cli_upgrade_cmd_ignores_down_script_content(runner, context, schema_dir, respx_mock, down_script):
    """Test fails if `esmigrate upgrade` parses a down script"""
    write_schema(schema_dir, "V1_0__create_twitter.up.esm", 'PUT twitter\n{"settings": {}}')
    write_schema(schema_dir, "V1_0__create_twitter.down.esm", down_script)
    respx_mock.put(f"{ES_HOST}/twitter").respond(200, json={"acknowledged": True})
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert [row.success for row in stored_rows(context)] == [True]


def test_cli_upgrade_cmd_lists_illegal_file_names_before_any_request(runner, context, schema_dir, respx_mock):
    """Test fails if illegal file names are not all named with exit 31 before anything runs"""
    write_schema(schema_dir, "V1__first_bad.esm")
    write_schema(schema_dir, "V2__second_bad.esm")
    write_schema(schema_dir, "V3_0__create_twitter.esm")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_FILE
    assert "V1__first_bad.esm" in result.output
    assert "V2__second_bad.esm" in result.output
    assert len(respx_mock.calls) == 0
    assert not stored_rows(context)


def test_cli_upgrade_cmd_lists_invalid_pairs_before_any_request(runner, context, schema_dir, respx_mock):
    """Test fails if invalid sets of files are not all reported with exit 31 before anything runs"""
    write_schema(schema_dir, "V1_0__a.esm")
    write_schema(schema_dir, "V1_0__a.up.esm")
    write_schema(schema_dir, "V2_0__a.up.esm")
    write_schema(schema_dir, "V2_0__b.down.esm")
    write_schema(schema_dir, "V3_0__create_twitter.esm")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_FILE
    assert "1.0: plain and up/down files mixed" in result.output
    assert "2.0: up and down script names must match" in result.output
    assert len(respx_mock.calls) == 0
    assert not stored_rows(context)


def test_cli_upgrade_cmd_rejects_version_zero_file(runner, context, schema_dir, respx_mock):
    """Test fails if a file for version 0.0 is not rejected with exit 31"""
    write_schema(schema_dir, "V0_0__a.esm")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_FILE
    assert "0.0: version 0.0 is not allowed" in result.output
    assert len(respx_mock.calls) == 0


def test_cli_upgrade_cmd_records_failed_up_script(runner, context, schema_dir, respx_mock):
    """Test fails if a failing up script is not recorded by its own path and does not block a later upgrade"""
    write_schema(schema_dir, "V1_0__create_twitter.up.esm", 'PUT twitter\n{"settings": {}}')
    write_schema(schema_dir, "V1_0__create_twitter.down.esm", "DELETE twitter")
    respx_mock.put(f"{ES_HOST}/twitter").respond(500, json={"error": "boom"})
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_ES_HTTPERROR
    assert [(str(row.version), row.success, row.script) for row in stored_rows(context)] == [
        ("1.0", False, "V1_0__create_twitter.up.esm"),
    ]
    assert invoke(runner, "upgrade").exit_code == Errors.ERR_DB_IN_ERROR_STATE


def test_cli_upgrade_cmd_rejects_up_script_that_does_not_parse(runner, context, schema_dir, respx_mock):
    """Test fails if an up script that does not parse records anything or does not exit 32"""
    write_schema(schema_dir, "V1_0__create_twitter.up.esm", "THIS IS NOT A COMMAND")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_COMMAND
    assert "V1_0__create_twitter.up.esm: Unexpected command found: THIS" in result.output
    assert stored_rows(context) == []
    assert len(respx_mock.calls) == 0


@pytest.mark.parametrize("name", ["V1_0__empty.esm", "V1_0__empty.up.esm"])
def test_cli_upgrade_cmd_fails_for_empty_up_script(runner, context, schema_dir, respx_mock, name):
    """Test fails if an empty up or plain script is not a script error, unlike a down-only migration"""
    write_schema(schema_dir, name, "")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_COMMAND
    assert f"{name}: Script does not contain any command" in result.output
    assert stored_rows(context) == []
    assert len(respx_mock.calls) == 0


def test_cli_upgrade_cmd_skips_applied_version_written_with_leading_zeros(runner, context, schema_dir, respx_mock):
    """Test fails if a v2 row stored as 1.01 is not copied as version 1.1 and counted as applied"""
    create_v2_table(context, [("default", "1.01", 1, 1)])
    assert invoke(runner, "init").exit_code == 0
    write_schema(schema_dir, "V1_01__first.esm", 'PUT first\n{"settings": {}}')
    write_schema(schema_dir, "V1_2__second.esm", 'PUT second\n{"settings": {}}')
    respx_mock.put(f"{ES_HOST}/second").respond(200, json={"acknowledged": True})
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert len(respx_mock.calls) == 1
    assert versions(context) == ["1.1", "1.2"]


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


def hold_lock(context, host="other-host", pid=4242):
    async def insert_row():
        async with DBManager.connect(context.schema_db, namespace=context.schema_namespace) as db:
            async with db.lock():
                pass
            async with db._engine.begin() as conn:
                await conn.execute(
                    insert(LOCK_TABLE).values(
                        namespace=context.schema_namespace,
                        owner_host=host,
                        owner_pid=pid,
                        acquired_at=datetime.now(UTC),
                    )
                )

    asyncio.run(insert_row())


def lock_rows(context):
    async def fetch():
        async with DBManager.connect(context.schema_db) as db, db._engine.connect() as conn:
            return (await conn.execute(select(LOCK_TABLE))).mappings().all()

    return asyncio.run(fetch())


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


def test_cli_upgrade_cmd_records_every_run_in_the_history(runner, context, schema_dir, respx_mock):
    """Test fails if successful runs are not recorded as up rows in the history with their results"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    write_schema(schema_dir, "V1_1__read_twitter.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200, json={"ok": True})
    assert invoke(runner, "upgrade").exit_code == 0
    history = history_rows(context)
    assert [(entry.operation, entry.version_base, entry.version_rank, entry.success) for entry in history] == [
        ("up", 1, 0, True),
        ("up", 1, 1, True),
    ]
    assert [entry.script for entry in history] == ["V1_0__create_twitter.esm", "V1_1__read_twitter.esm"]
    assert history[0].query_results == stored_rows(context)[0].query_results


def test_cli_upgrade_cmd_commits_running_rows_before_the_first_request(runner, context, schema_dir, respx_mock):
    """Test fails if the running state row and history row are not committed before the first request is sent"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    seen = []

    def inspect_database(request):
        seen.append(raw_rows(context, "SELECT success FROM esm_schema_state"))
        seen.append(raw_rows(context, "SELECT success FROM esm_schema_history"))
        return httpx.Response(200)

    respx_mock.get(f"{ES_HOST}/twitter").mock(side_effect=inspect_database)
    assert invoke(runner, "upgrade").exit_code == 0
    assert seen == [[(None,)], [(None,)]]


def test_cli_upgrade_cmd_stores_execution_time_in_milliseconds(runner, context, schema_dir, respx_mock):
    """Test fails if execution_time is not stored in milliseconds"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")

    def slow_response(request):
        time.sleep(0.03)
        return httpx.Response(200)

    respx_mock.get(f"{ES_HOST}/twitter").mock(side_effect=slow_response)
    assert invoke(runner, "upgrade").exit_code == 0
    (row,) = stored_rows(context)
    assert row.execution_time is not None
    assert row.execution_time >= 25


@pytest.mark.parametrize("error", [httpx.ReadTimeout("slow"), httpx.ReadError("cut")])
def test_cli_upgrade_cmd_marks_failed_when_elasticsearch_may_have_applied_the_request(
    runner, context, schema_dir, respx_mock, error
):
    """Test fails if a failure after the request may have reached elasticsearch is not recorded as failed"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    respx_mock.get(f"{ES_HOST}/twitter").mock(side_effect=error)
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_ES_CONNERROR
    assert [(str(row.version), row.success) for row in stored_rows(context)] == [("1.0", False)]
    assert [entry.success for entry in history_rows(context)] == [False]


def test_cli_upgrade_cmd_marks_failed_on_connection_error_after_first_request(runner, context, schema_dir, respx_mock):
    """Test fails if a connection error after a completed request does not mark the run failed with both results"""
    write_schema(schema_dir, "V1_0__create_twitter.esm", "PUT twitter\nPUT twitter/_doc/1")
    respx_mock.put(f"{ES_HOST}/twitter").respond(200, json={"acknowledged": True})
    respx_mock.put(f"{ES_HOST}/twitter/_doc/1").mock(side_effect=httpx.ConnectError("refused"))
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_ES_CONNERROR
    (row,) = stored_rows(context)
    assert row.success is False
    assert row.query_results is not None
    assert [json.loads(item)["status"] for item in row.query_results.split(";")] == [200, None]


def test_cli_upgrade_cmd_lists_every_script_that_does_not_parse(runner, context, schema_dir, respx_mock):
    """Test fails if a valid earlier script runs, or not every unparseable script is listed, before exit 32"""
    write_schema(schema_dir, "V1_0__valid.esm")
    write_schema(schema_dir, "V1_1__wrong_verb.esm", "PATCH twitter")
    write_schema(schema_dir, "V1_2__valid_too.esm")
    write_schema(schema_dir, "V1_3__absolute_url.esm", "GET http://other.example.com/twitter")
    write_schema(schema_dir, "V1_4__down_only.down.esm", "NOT A COMMAND")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_COMMAND
    assert "InvalidCommandScriptError: Invalid migration scripts:" in result.output
    assert "  V1_1__wrong_verb.esm: Unexpected command found: PATCH" in result.output
    assert "  V1_3__absolute_url.esm: Unexpected URL scheme found: http://other.example.com/twitter" in result.output
    assert "V1_4__down_only" not in result.output
    assert len(respx_mock.calls) == 0
    assert stored_rows(context) == []
    assert history_rows(context) == []


def test_cli_upgrade_cmd_warns_about_unapplied_migrations_below_latest(runner, context, schema_dir, respx_mock):
    """Test fails if migrations below the latest applied version are applied or skipped without naming their files"""
    seed(context, ("1.0", True), ("3.0", True))
    write_schema(schema_dir, "V1_0__first.esm")
    write_schema(schema_dir, "V2_0__second.up.esm")
    write_schema(schema_dir, "V2_0__second.down.esm", "DELETE twitter")
    write_schema(schema_dir, "V2_5__dropped.down.esm", "DELETE twitter")
    write_schema(schema_dir, "V3_0__third.esm")
    write_schema(schema_dir, "V4_0__fourth.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0, result.output
    assert (
        "WARNING: Migrations below the latest applied version 3.0 are skipped:\n"
        "  2.0: V2_0__second.up.esm, V2_0__second.down.esm\n"
        "  2.5: V2_5__dropped.down.esm\n"
    ) in result.stderr
    assert len(respx_mock.calls) == 1
    assert versions(context) == ["1.0", "3.0", "4.0"]


@pytest.mark.parametrize("args", [["upgrade"], ["-q", "upgrade", "-s", "1.0"]])
def test_cli_upgrade_cmd_warns_about_unapplied_migrations_before_nothing_to_do(runner, context, schema_dir, args):
    """Test fails if the unapplied-migration warning depends on pending work, -q or the requested version"""
    seed(context, ("1.0", True), ("3.0", True))
    write_schema(schema_dir, "V2_0__second.esm")
    write_schema(schema_dir, "V3_0__third.esm")
    result = runner.invoke(cli.main, ["--profile", "test", *args])
    assert result.exit_code == 0
    assert "WARNING: Migrations below the latest applied version 3.0 are skipped:\n  2.0: V2_0__second.esm" in (
        result.stderr
    )


def test_cli_upgrade_cmd_does_not_warn_without_unapplied_migrations(runner, context, schema_dir, respx_mock):
    """Test fails if the unapplied-migration warning appears when every lower migration was applied"""
    seed(context, ("1.0", True))
    write_schema(schema_dir, "V1_0__first.esm")
    write_schema(schema_dir, "V2_0__second.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "are skipped" not in result.output
