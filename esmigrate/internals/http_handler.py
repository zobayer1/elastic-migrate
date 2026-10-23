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
)


class HTTPHandler:
    def __init__(self, ctx: ContextConfig) -> None:
        self._ctx = ctx
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            base_url=self._ctx.es_host,
            headers=self._ctx.headers,
            timeout=self._ctx.es_timeout,
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

        try:
            response = await self._client.request(
                command.verb, command.path, content=command.body, headers=command.head
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise ElasticsearchHTTPError(err.response) from err
        except httpx.TransportError as err:
            raise ElasticsearchConnError(f"{type(err).__name__}: {err}") from err

        return response
