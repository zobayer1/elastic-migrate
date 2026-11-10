import json
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest

from esmigrate.commons import Command, old_timestamp_to_utc, query_error_string, query_results_string
from esmigrate.exceptions import ElasticsearchConnError


def test_query_results_string_records_query_status_and_response():
    """Test fails if a stored result does not hold the query, the status code and the response text"""
    response = httpx.Response(201, text='{"acknowledged":true}')
    stored = json.loads(query_results_string(Command("PUT", "/twitter", '{"a":1}\n'), response))
    assert stored == {"query": 'PUT /twitter {"a":1}\n', "status": 201, "result": '{"acknowledged":true}'}


def test_query_error_string_records_the_error_without_a_status():
    """Test fails if a request that got no response is not stored in the usual format with a null status"""
    stored = json.loads(query_error_string(Command("GET", "/twitter"), ElasticsearchConnError("ConnectError: refused")))
    assert stored == {
        "query": "GET /twitter None",
        "status": None,
        "result": "ElasticsearchConnError: ConnectError: refused",
    }


def test_old_timestamp_to_utc_keeps_missing_timestamps():
    """Test fails if a missing timestamp gets a fabricated value"""
    assert old_timestamp_to_utc(None) is None


def test_old_timestamp_to_utc_converts_aware_timestamps():
    """Test fails if a timestamp with a time zone is not converted to UTC"""
    aware = datetime(2021, 6, 16, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    assert old_timestamp_to_utc(aware, force_utc=True) == datetime(2021, 6, 16, 10, 0, tzinfo=UTC)


@pytest.mark.usefixtures("local_time_plus_six")
@pytest.mark.parametrize(
    ("value", "force_utc", "expected"),
    [
        (datetime(2021, 6, 16, 12, 0), False, datetime(2021, 6, 16, 6, 0, tzinfo=UTC)),
        (datetime(2021, 6, 16, 12, 0), True, datetime(2021, 6, 16, 12, 0, tzinfo=UTC)),
        ("2021-06-16 12:00:00.123456", False, datetime(2021, 6, 16, 6, 0, 0, 123456, tzinfo=UTC)),
        ("2021-06-16 12:00:00.123456", True, datetime(2021, 6, 16, 12, 0, 0, 123456, tzinfo=UTC)),
    ],
)
def test_old_timestamp_to_utc_reads_naive_timestamps_as_local_or_utc(value, force_utc, expected):
    """Test fails if naive v1 timestamps are not read as local time or naive v2 timestamps are shifted"""
    result = old_timestamp_to_utc(value, force_utc)
    assert result == expected
    assert result is not None
    assert result.tzinfo == UTC
