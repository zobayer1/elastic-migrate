# -*- coding: utf-8 -*-


class Command(object):
    def __init__(self, verb: str, path: str, body: str = None, head: dict = None):
        self.verb = verb
        self.path = path
        self.body = body
        self.head = head if head else {}

    @property
    def verb(self):
        return self._verb

    @verb.setter
    def verb(self, value: str):
        self._verb = value

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value: str):
        self._path = value

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, value: str):
        self._body = value

    @property
    def head(self):
        return self._head

    @head.setter
    def head(self, value: dict):
        self._head = value
