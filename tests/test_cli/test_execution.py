import json

import httpx

from esmigrate.cli.execution import query_error_string, query_results_string
from esmigrate.commons import Command
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
