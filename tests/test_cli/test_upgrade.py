import json
import ssl
import time

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from esmigrate import cli
from esmigrate.commons.script_data import make_sha1
from esmigrate.exceptions import Errors, SchemaVersionSqlDbError
from tests.test_cli.helpers import (
    ES_HOST,
    create_v2_table,
    history_rows,
    invoke,
    raw_rows,
    seed,
    stored_rows,
    versions,
    write_schema,
)


@pytest.mark.parametrize("schema_version", ["invalid", "1.2.3", "1.x", "2147483648", "1.2147483648"])
def test_cli_upgrade_cmd_fails_with_value_error(runner, context, schema_version):
    """Test fails if `esmigrate upgrade` fails to check invalid schema version parameter"""
    result = invoke(runner, "upgrade", "--schema-version", schema_version)
    assert result.exit_code == Errors.ERR_INVALID_SCMVER


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
    assert "No migration scripts found, nothing to do" in result.output


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
    """Test fails if `esmigrate upgrade` does not stop and record a failed row on an Elasticsearch error response"""
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
    """Test fails if a first request that never reached Elasticsearch leaves a state row or loses its history"""
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
    assert "Applying migration 1.9 (V1_9__step_1_9.esm)" not in result.output
    assert "Applying migration 1.10 (V1_10__step_1_10.esm)" in result.output
    assert "Schema database upgraded to 1.10" in result.output


def test_cli_upgrade_cmd_stops_at_double_digit_requested_version(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade --schema-version 1.10` does not stop at 1.10"""
    for sequence in (9, 10, 11):
        write_schema(schema_dir, f"V1_{sequence}__step_1_{sequence}.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade", "--schema-version", "1.10")
    assert result.exit_code == 0
    assert "Applying migration 1.9 (V1_9__step_1_9.esm)" in result.output
    assert "Applying migration 1.10 (V1_10__step_1_10.esm)" in result.output
    assert "Applying migration 1.11 (V1_11__step_1_11.esm)" not in result.output
    assert "Schema database upgraded to 1.10" in result.output


def test_cli_upgrade_cmd_treats_zero_version_as_explicit_target(runner, context, schema_dir):
    """Test fails if `esmigrate upgrade --schema-version 0` is treated as 'latest'"""
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    result = invoke(runner, "upgrade", "--schema-version", "0")
    assert result.exit_code == 0
    assert "Applying migration" not in result.output
    assert "No migrations to apply up to version 0.0 (database at 0.0), nothing to do" in result.output


def test_cli_upgrade_cmd_uses_profile_namespace(runner, context, schema_dir, respx_mock):
    """Test fails if `esmigrate upgrade` ignores the profile schema namespace"""
    seed(context, ("1.0", True))
    context.schema_namespace = "billing"
    write_schema(schema_dir, "V1_0__create_twitter.esm")
    respx_mock.get(f"{ES_HOST}/twitter").respond(200)
    result = invoke(runner, "upgrade")
    assert result.exit_code == 0
    assert "Applying migration 1.0 (V1_0__create_twitter.esm)" in result.output
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
    assert "Recording migration 1.0 without requests, it has no up script" in result.output
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
    assert "Applying migration" not in result.output
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
    assert "1.0: Plain and up/down files mixed" in result.output
    assert "2.0: Up and down script names must match" in result.output
    assert len(respx_mock.calls) == 0
    assert not stored_rows(context)


def test_cli_upgrade_cmd_rejects_version_zero_file(runner, context, schema_dir, respx_mock):
    """Test fails if a file for version 0.0 is not rejected with exit 31"""
    write_schema(schema_dir, "V0_0__a.esm")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_FILE
    assert "0.0: Not allowed, 0.0 means nothing is applied" in result.output
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
    assert (
        "V1_0__create_twitter.up.esm: Script must start with a GET, PUT, POST or DELETE line, found 'THIS'"
        in result.output
    )
    assert stored_rows(context) == []
    assert len(respx_mock.calls) == 0


@pytest.mark.parametrize("name", ["V1_0__empty.esm", "V1_0__empty.up.esm"])
def test_cli_upgrade_cmd_fails_for_empty_up_script(runner, context, schema_dir, respx_mock, name):
    """Test fails if an empty up or plain script is not a script error, unlike a down-only migration"""
    write_schema(schema_dir, name, "")
    result = invoke(runner, "upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_COMMAND
    assert f"{name}: Script has no requests" in result.output
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
    """Test fails if a failure after the request may have reached Elasticsearch is not recorded as failed"""
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
    assert (
        "  V1_1__wrong_verb.esm: Script must start with a GET, PUT, POST or DELETE line, found 'PATCH'" in result.output
    )
    assert (
        "  V1_3__absolute_url.esm: Absolute URL not allowed: 'http://other.example.com/twitter', "
        "use a path such as /index" in result.output
    )
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
