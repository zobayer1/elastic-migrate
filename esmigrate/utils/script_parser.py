# -*- coding: utf-8 -*-
import re

from esmigrate.exceptions import InvalidCommandScript, InvalidCommandVerb


class ScriptParser(object):

    def __init__(self):
        self.verbs = ['GET', 'PUT', 'POST', 'DELETE']
        self._sverbs = '|'.join(self.verbs)
        self._pattern = re.compile(r'^(GET|PUT|POST|DELETE)\s+(.*)$', re.M | re.I)

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
            yield verb, path
