# -*- coding: utf-8 -*-


class Header(object):

    def __init__(self, header: dict):
        self._dict = header

    def dict(self):
        return self._dict
