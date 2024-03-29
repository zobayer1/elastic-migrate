# -*- coding: utf-8 -*-
import requests
from requests.exceptions import HTTPError, ConnectionError

from esmigrate.commons import Command, http_verbs
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidCommandVerbError, ElasticsearchConnError


class HTTPHandler(object):
    def __init__(self, ctx: ContextConfig = None):
        self._ctx = ctx
        self._session = requests.session()

    def init_ctx(self, ctx: ContextConfig):
        self._ctx = ctx

    def make_requests(self, command: Command):
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
            raise ElasticsearchConnError(err)

        return response
