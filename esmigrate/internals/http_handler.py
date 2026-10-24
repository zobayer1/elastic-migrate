import logging
import ssl
import time
from types import TracebackType
from typing import Self

import httpx

from esmigrate.commons import Command, http_verbs
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    ContextObjectNotSetError,
    ElasticsearchConnError,
    ElasticsearchHTTPError,
    InvalidCommandVerbError,
    InvalidConfigurationError,
)

log = logging.getLogger(__name__)


def build_ssl_context(ctx: ContextConfig) -> ssl.SSLContext:
    try:
        context = ssl.create_default_context(cafile=ctx.es_ca_certs)
        if not ctx.es_verify_certs:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        if ctx.es_client_cert:
            context.load_cert_chain(ctx.es_client_cert, ctx.es_client_key, ctx.es_client_key_password)
    except (ssl.SSLError, OSError) as err:
        raise InvalidConfigurationError(f"Cannot load TLS certificates: {err}") from err
    return context


def find_tls_error(err: BaseException) -> ssl.SSLError | None:
    seen: set[int] = set()
    current: BaseException | None = err
    while current is not None and id(current) not in seen:
        if isinstance(current, ssl.SSLError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


class HTTPHandler:
    def __init__(self, ctx: ContextConfig) -> None:
        self._ctx = ctx
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        headers = dict(self._ctx.headers)
        if self._ctx.es_api_key:
            headers["Authorization"] = f"ApiKey {self._ctx.es_api_key}"
        auth = None
        if self._ctx.es_username is not None and self._ctx.es_password is not None:
            auth = httpx.BasicAuth(self._ctx.es_username, self._ctx.es_password)
        self._client = httpx.AsyncClient(
            base_url=self._ctx.es_host,
            headers=headers,
            auth=auth,
            timeout=self._ctx.es_timeout,
            verify=build_ssl_context(self._ctx),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def make_requests(self, command: Command) -> httpx.Response:
        if self._client is None:
            raise ContextObjectNotSetError("HTTP client is not open, use `async with HTTPHandler(ctx)`")

        if command.verb not in http_verbs:
            raise InvalidCommandVerbError(f"Unexpected verb found: {command.verb}")

        sent = len(command.body.encode()) if command.body else 0
        started = time.perf_counter()
        try:
            response = await self._client.request(
                command.verb, command.path, content=command.body, headers=command.head
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            log.debug(
                f"{command.verb} {command.path} ({sent} bytes) -> {response.status_code} "
                f"({len(response.content)} bytes) in {elapsed} ms"
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise ElasticsearchHTTPError(err.response) from err
        except (httpx.TransportError, ssl.SSLError) as err:
            tls_error = find_tls_error(err)
            if tls_error is not None:
                message = (
                    f"TLS error: {tls_error}, check elastic_ca_certs, elastic_verify_certs and client certificates"
                )
                raise ElasticsearchConnError(message) from err
            raise ElasticsearchConnError(f"{type(err).__name__}: {err}") from err

        return response
