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
        if command.verb == 'GET':
            print('Received a GET request')
        elif command.verb == 'PUT':
            print('Received a PUT request')
        elif command.verb == 'POST':
            print('Received a POST request')
        elif command.verb == 'DELETE':
            print('Received a DELETE request')
        else:
            raise InvalidCommandVerbError(f'Unexpected verb found: "{command.verb}"')
        return command.verb
