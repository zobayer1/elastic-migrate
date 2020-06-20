# -*- coding: utf-8 -*-
import re

from esmigrate.contexts.context_config import ContextConfig
from esmigrate.exceptions import InvalidCommandScript, InvalidCommandVerb
from esmigrate.utils.command import Command


class ScriptParser(object):

    def __init__(self, ctx: ContextConfig = None):
        self.verbs = ['GET', 'PUT', 'POST', 'DELETE']
        self._sverbs = '|'.join(self.verbs)
        self._pattern = re.compile(r'^(GET|PUT|POST|DELETE)\s+(.*)$', re.M | re.I)
        self._ctx = ctx

    def init_ctx(self, ctx: ContextConfig):
        self._ctx = ctx

    def get_ctx_profile(self):
        return self._ctx.profile if self._ctx else None

    def get_commands(self, script_text: str):
        stripped_lines = [line.strip() for line in script_text.split('\n') if len(line.strip()) > 0]
        occurs = [idx for idx, line in enumerate(stripped_lines) if self._pattern.match(line)]
        if len(occurs) == 0 or occurs[0] != 0:
            raise InvalidCommandScript(f'Expected "{self._sverbs} {{path}}", found: "{stripped_lines[0].split()[0]}"')
        for line in occurs:
            m = self._pattern.match(stripped_lines[line])
            verb, path = m.group(1), m.group(2)
            if verb not in self.verbs:
                raise InvalidCommandVerb(f'Expected "{self._sverbs} {{path}}", found: "{m.group(1)}"')
            yield Command(verb, path)
