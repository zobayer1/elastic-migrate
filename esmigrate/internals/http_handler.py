import requests
from requests.exceptions import ConnectionError, HTTPError

from esmigrate.commons import Command, http_verbs
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, ElasticsearchConnError, InvalidCommandVerbError


class HTTPHandler:
    def __init__(self, ctx: ContextConfig | None = None) -> None:
        self._ctx = ctx
        self._session = requests.session()

    def init_ctx(self, ctx: ContextConfig) -> None:
        self._ctx = ctx

    def make_requests(self, command: Command) -> requests.Response:
        if self._ctx is None:
            raise ContextObjectNotSetError("Context was not set")

        if command.verb not in http_verbs:
            raise InvalidCommandVerbError(f"Unexpected verb found: {command.verb}")

        for k, v in self._ctx.headers.items():
            command.head[k] = v

        try:
            response = self._session.request(command.verb, url=command.path, data=command.body, headers=command.head)
            response.raise_for_status()
        except HTTPError:
            raise
        except ConnectionError as err:
            raise ElasticsearchConnError(err) from err

        return response
