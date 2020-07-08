# -*- coding: utf-8 -*-


class ScriptData(object):
    def __init__(self, ver: int, seq: int, name: str, ext: str):
        self.version_base = ver
        self.version_rank = seq
        self.description = f"{name}.{ext}"
        self.version = f"{ver}.{seq}"
