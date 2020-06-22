# -*- coding: utf-8 -*-


class Header(object):

    def __init__(self, header: dict):
        self._dict = header

    def dict(self):
        return self._dict

    def is_json_header(self):
        return self._dict.get('Content-Type') == 'application/json'

    def is_ndjson_header(self):
        return self._dict.get('Content-Type') == 'application/x-ndjson'

    def __str__(self):
        return str(self._dict)
