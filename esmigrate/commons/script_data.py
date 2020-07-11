# -*- coding: utf-8 -*-
from hashlib import sha1


class ScriptData(object):
    def __init__(self, version: int, sequence: int, name: str, extension: str, path: str, content: str):
        self.version_base = version
        self.version_rank = sequence
        self.description = f"{name}.{extension}"
        self.version = f"{version}.{sequence}"
        self.path = path
        self.content = content
        self.checksum = ScriptData.make_sha1(content)

    @staticmethod
    def make_sha1(s, encoding="utf-8"):
        return sha1(s.encode(encoding)).digest()
