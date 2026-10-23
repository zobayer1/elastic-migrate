import httpx
import pytest

from esmigrate.commons import Command
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    ContextObjectNotSetError,
    ElasticsearchConnError,
    ElasticsearchHTTPError,
    InvalidCommandVerbError,
)
from esmigrate.internals import HTTPHandler

ES_HOST = "http://es.example.com:9200"


@pytest.fixture
def context():
    """pytest fixture for providing a context pointing to a fake elasticsearch host"""
    ctx = ContextConfig()
    ctx.es_host = ES_HOST
    ctx.headers = {"X-Profile": "test"}
    return ctx


@pytest.fixture
async def http_handler(context):
    """pytest fixture for providing an open HTTPHandler"""
    async with HTTPHandler(context) as handler:
        yield handler


@pytest.mark.parametrize(("verb", "status"), [("GET", 200), ("PUT", 200), ("POST", 201), ("DELETE", 200)])
async def test_http_handler_sends_request_relative_to_host(http_handler, respx_mock, verb, status):
    """Test fails if http handler does not send each verb to the path relative to the configured host"""
    route = respx_mock.request(verb, f"{ES_HOST}/twitter/_doc").respond(status, text="ok")
    response = await http_handler.make_requests(Command(verb, "/twitter/_doc"))
    assert route.called
    assert response.status_code == status
    assert response.text == "ok"


async def test_http_handler_keeps_base_url_path_prefix(context, respx_mock):
    """Test fails if a host with a path prefix (e.g. behind a proxy) is not preserved"""
    context.es_host = f"{ES_HOST}/es"
    route = respx_mock.get(f"{ES_HOST}/es/twitter").respond(200)
    async with HTTPHandler(context) as handler:
        await handler.make_requests(Command("GET", "/twitter"))
    assert route.called


async def test_http_handler_sends_profile_and_command_headers(http_handler, respx_mock):
    """Test fails if profile headers and command headers are not both sent, with the command header winning"""
    route = respx_mock.post(f"{ES_HOST}/_bulk").respond(200)
    command = Command("POST", "/_bulk", '{"index": {}}\n{}', {"Content-Type": "application/x-ndjson"})
    await http_handler.make_requests(command)
    request = route.calls.last.request
    assert request.headers["X-Profile"] == "test"
    assert request.headers["Content-Type"] == "application/x-ndjson"
    assert request.content == b'{"index": {}}\n{}'


async def test_http_handler_applies_configured_timeout(context):
    """Test fails if the profile timeout is not applied to the client"""
    context.es_timeout = 12.5
    async with HTTPHandler(context) as handler:
        assert handler._client is not None
        assert handler._client.timeout == httpx.Timeout(12.5)


async def test_http_handler_allows_disabled_timeout(context):
    """Test fails if a null timeout does not disable client timeouts"""
    context.es_timeout = None
    async with HTTPHandler(context) as handler:
        assert handler._client is not None
        assert handler._client.timeout == httpx.Timeout(None)


async def test_http_handler_raises_invalid_command_verb_error(http_handler):
    """Test fails if http handler does not raise unsupported verb"""
    with pytest.raises(InvalidCommandVerbError):
        await http_handler.make_requests(Command("PATCH", "/twitter"))


async def test_http_handler_raises_http_error_with_response(http_handler, respx_mock):
    """Test fails if a non-2xx response is not raised as ElasticsearchHTTPError carrying the response"""
    respx_mock.get(f"{ES_HOST}/missing").respond(404, text="not found")
    with pytest.raises(ElasticsearchHTTPError, match="404 Not Found for GET /missing") as err:
        await http_handler.make_requests(Command("GET", "/missing"))
    assert err.value.response.text == "not found"


@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("timed out")])
async def test_http_handler_raises_connection_error(http_handler, respx_mock, error):
    """Test fails if connection failures and timeouts are not raised as ElasticsearchConnError"""
    respx_mock.get(f"{ES_HOST}/twitter").mock(side_effect=error)
    with pytest.raises(ElasticsearchConnError, match=type(error).__name__):
        await http_handler.make_requests(Command("GET", "/twitter"))


async def test_http_handler_requires_open_client(context):
    """Test fails if requests are allowed outside the async context manager"""
    with pytest.raises(ContextObjectNotSetError):
        await HTTPHandler(context).make_requests(Command("GET", "/twitter"))


async def test_http_handler_closes_client_on_exit(context):
    """Test fails if the client is not closed when the async context manager exits, including on errors"""
    handler = await HTTPHandler(context).__aenter__()
    client = handler._client
    assert client is not None
    await handler.__aexit__(RuntimeError, RuntimeError("boom"), None)
    assert client.is_closed
    assert handler._client is None


async def test_http_handler_exit_without_enter_is_safe(context):
    """Test fails if exiting a handler that was never opened raises"""
    await HTTPHandler(context).__aexit__(None, None, None)
