import base64
import ssl

import httpx
import pytest
import trustme
from cryptography.hazmat.primitives import serialization

from esmigrate.commons import Command
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    ContextObjectNotSetError,
    ElasticsearchConnError,
    ElasticsearchHTTPError,
    InvalidCommandVerbError,
    InvalidConfigurationError,
)
from esmigrate.internals import HTTPHandler
from esmigrate.internals.http_handler import build_ssl_context, find_tls_error

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


@pytest.fixture(scope="module")
def ca():
    """pytest fixture for a throwaway certificate authority"""
    return trustme.CA()


@pytest.fixture
def certs(tmp_path, ca):
    """pytest fixture writing CA, client chain, separate cert/key and an encrypted key to files"""
    client = ca.issue_cert("migrator.example.com")
    paths = {name: tmp_path / name for name in ("ca.pem", "chain.pem", "cert.pem", "key.pem", "encrypted.pem")}
    ca.cert_pem.write_to_path(str(paths["ca.pem"]))
    client.private_key_and_cert_chain_pem.write_to_path(str(paths["chain.pem"]))
    paths["cert.pem"].write_bytes(b"".join(blob.bytes() for blob in client.cert_chain_pems))
    client.private_key_pem.write_to_path(str(paths["key.pem"]))
    key = serialization.load_pem_private_key(client.private_key_pem.bytes(), password=None)
    paths["encrypted.pem"].write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b"key-password"),
        )
    )
    return {name: str(path) for name, path in paths.items()}


def test_build_ssl_context_verifies_by_default(context):
    """Test fails if the default SSL context does not verify certificates and host names"""
    ssl_context = build_ssl_context(context)
    assert ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert ssl_context.check_hostname is True


def test_build_ssl_context_loads_ca_bundle(context, certs):
    """Test fails if elastic_ca_certs is not the trust store of the SSL context"""
    context.es_ca_certs = certs["ca.pem"]
    assert len(build_ssl_context(context).get_ca_certs()) == 1


def test_build_ssl_context_can_disable_verification(context):
    """Test fails if elastic_verify_certs false does not disable certificate and host name checks"""
    context.es_verify_certs = False
    ssl_context = build_ssl_context(context)
    assert ssl_context.verify_mode == ssl.CERT_NONE
    assert ssl_context.check_hostname is False


@pytest.mark.parametrize(
    ("cert", "key", "password"),
    [("chain.pem", None, None), ("cert.pem", "key.pem", None), ("cert.pem", "encrypted.pem", "key-password")],
)
def test_build_ssl_context_loads_client_certificate(context, certs, cert, key, password):
    """Test fails if a combined chain, a separate key, or an encrypted key cannot be loaded for mTLS"""
    context.es_client_cert = certs[cert]
    context.es_client_key = certs[key] if key else None
    context.es_client_key_password = password
    assert isinstance(build_ssl_context(context), ssl.SSLContext)


@pytest.mark.parametrize(
    ("field", "value"),
    [("es_client_key_password", "wrong-password"), ("es_ca_certs", "garbage.pem")],
)
def test_build_ssl_context_rejects_unusable_certificates(context, certs, tmp_path, field, value):
    """Test fails if a wrong key password or an invalid CA file is not reported as a configuration error"""
    (tmp_path / "garbage.pem").write_text("not a certificate")
    context.es_client_cert = certs["cert.pem"]
    context.es_client_key = certs["encrypted.pem"]
    context.es_client_key_password = "key-password"
    setattr(context, field, str(tmp_path / value) if value.endswith(".pem") else value)
    with pytest.raises(InvalidConfigurationError, match="Cannot load TLS certificates"):
        build_ssl_context(context)


async def test_http_handler_passes_ssl_context_to_client(context, mocker):
    """Test fails if the client is not created with the SSL context built from the profile"""
    context.es_verify_certs = False
    client_init = mocker.spy(httpx.AsyncClient, "__init__")
    async with HTTPHandler(context):
        pass
    verify = client_init.call_args.kwargs["verify"]
    assert isinstance(verify, ssl.SSLContext)
    assert verify.verify_mode == ssl.CERT_NONE


async def test_http_handler_sends_basic_auth(context, respx_mock):
    """Test fails if elastic_username/elastic_password are not sent as basic auth"""
    context.es_username, context.es_password = "migrator", "s3cr3t"
    route = respx_mock.get(f"{ES_HOST}/").respond(200)
    async with HTTPHandler(context) as handler:
        await handler.make_requests(Command("GET", "/"))
    expected = base64.b64encode(b"migrator:s3cr3t").decode()
    assert route.calls.last.request.headers["Authorization"] == f"Basic {expected}"


async def test_http_handler_sends_api_key(context, respx_mock):
    """Test fails if elastic_api_key is not sent as an ApiKey Authorization header"""
    context.es_api_key = "encoded-key"
    route = respx_mock.get(f"{ES_HOST}/").respond(200)
    async with HTTPHandler(context) as handler:
        await handler.make_requests(Command("GET", "/"))
    assert route.calls.last.request.headers["Authorization"] == "ApiKey encoded-key"
    assert route.calls.last.request.headers["X-Profile"] == "test"


async def test_http_handler_reports_tls_errors(http_handler, mocker):
    """Test fails if certificate failures are not reported as TLS errors with configuration hints"""
    error = httpx.ConnectError("handshake failed")
    error.__cause__ = ssl.SSLCertVerificationError(1, "certificate verify failed: unable to get local issuer")
    mocker.patch.object(http_handler._client, "request", side_effect=error)
    with pytest.raises(ElasticsearchConnError, match=r"TLS error: .*certificate verify failed.*elastic_ca_certs"):
        await http_handler.make_requests(Command("GET", "/twitter"))


def test_find_tls_error_stops_on_cyclic_exception_chains():
    """Test fails if a cyclic __cause__/__context__ chain makes the TLS error lookup loop forever"""
    first, second = httpx.ConnectError("first"), httpx.ConnectError("second")
    first.__context__, second.__context__ = second, first
    assert find_tls_error(first) is None
