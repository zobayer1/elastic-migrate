# -*- coding: utf-8 -*-
import requests

from esmigrate.commons import Command
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidCommandVerbError


class HTTPHandler(object):

    def __init__(self, ctx: ContextConfig = None):
        self._ctx = ctx
        self._session = requests.session()

    def init_ctx(self, ctx: ContextConfig):
        self._ctx = ctx

    def get_ctx(self):
        return self._ctx

    def make_requests(self, command: Command):
        if self._ctx is None:
            raise ContextObjectNotSetError('Context not set')
        for k, v in self._ctx.headers.items():
            command.head[k] = v
        if command.verb == 'GET':
            response = self._session.get(url=command.path, data=command.body, headers=command.head)
        elif command.verb == 'PUT':
            response = self._session.put(url=command.path, data=command.body, headers=command.head)
        elif command.verb == 'POST':
            response = self._session.post(url=command.path, data=command.body, headers=command.head)
        elif command.verb == 'DELETE':
            response = self._session.delete(url=command.path, data=command.body, headers=command.head)
        else:
            raise InvalidCommandVerbError(f'Unexpected verb found: "{command.verb}"')
        response.raise_for_status()
        return response
