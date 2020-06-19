# -*- coding: utf-8 -*-


class ScriptParser(object):

    def __init__(self):
        self.verbs = ['GET', 'PUT', 'POST', 'DELETE']

    def get_commands(self, script_text: str):
        stripped_lines = [line.strip() for line in script_text.split('\n') if len(line.strip()) > 0]
        occurs = [idx for idx, line in enumerate(stripped_lines) if line.startswith(tuple(self.verbs))]
        for line in occurs:
            yield stripped_lines[line]
