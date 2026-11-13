import httpx
import pytest

from esmigrate import cli
from esmigrate.exceptions import Errors
from tests.test_cli.helpers import (
    ES_HOST,
    invoke,
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


@pytest.mark.parametrize("command", ["init", "config", "upgrade", "rollback", "reset", "unlock"])
def test_cli_subcommand_help_works_without_profile(runner, command):
    """Test fails if `esmigrate <command> --help` needs a loadable profile"""
    result = runner.invoke(cli.main, ["--profile", "no-such-profile", command, "--help"])
    assert result.exit_code == 0, result.output
    assert f"Usage: main {command} [OPTIONS]" in result.output
    assert "Loading profile" not in result.output
