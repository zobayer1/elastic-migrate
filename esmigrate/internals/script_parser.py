# -*- coding: utf-8 -*-
import re

from esmigrate.commons import Command, is_valid_path, is_valid_json, JSON_HEADER, is_valid_ndjson, NDJSON_HEADER
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import InvalidCommandScript, InvalidCommandVerb, ContextNotSet, InvalidCommandPath, \
    InvalidCommandBody


class ScriptParser(object):

    def __init__(self, ctx: ContextConfig = None):
        self.verbs = ['GET', 'PUT', 'POST', 'DELETE']
        self._sverbs = '|'.join(self.verbs)
        self._pattern = re.compile(r'^(GET|PUT|POST|DELETE)\s+(.*)$', re.M | re.I)
        self._ctx = ctx

    def init_ctx(self, ctx: ContextConfig):
        self._ctx = ctx

    def get_ctx(self):
        return self._ctx

    def get_commands(self, script_text: str):
        if self._ctx is None:
            raise ContextNotSet('Context not set')
        stripped_lines = [line.strip() for line in script_text.split('\n') if len(line.strip()) > 0]
        occurs = [idx for idx, line in enumerate(stripped_lines) if self._pattern.match(line)]
        if len(occurs) == 0 or occurs[0] != 0:
            raise InvalidCommandScript(f'Expected "{self._sverbs} {{path}}", found: "{stripped_lines[0].split()[0]}"')
        occurs.append(len(stripped_lines))
        for idx in range(len(occurs) - 1):
            cmdline = occurs[idx]
            m = self._pattern.match(stripped_lines[cmdline])
            verb, path = m.group(1).strip(), m.group(2).strip()
            if verb not in self.verbs:
                raise InvalidCommandVerb(f'Expected "{self._sverbs} {{path}}", found: "{verb}"')
            if not is_valid_path(self._ctx.es_host, path):
                raise InvalidCommandPath(f'Illegal path "{path}"')
            cmdnext = occurs[idx + 1]
            if cmdline + 1 >= cmdnext:
                body, head = None, None
            else:
                body = '\n'.join(stripped_lines[cmdline + 1: cmdnext])
                if is_valid_json(body):
                    head = JSON_HEADER.dict()
                elif is_valid_ndjson(body):
                    head = NDJSON_HEADER.dict()
                else:
                    raise InvalidCommandBody(f'Expected a {JSON_HEADER} or {NDJSON_HEADER} body')
            yield Command(verb, path, body, head)
