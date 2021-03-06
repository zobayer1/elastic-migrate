# -*- coding: utf-8 -*-
import glob
import os
import re

from esmigrate.commons import parse_file_path, ScriptData
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidSchemaPatternError, InvalidSchemaFileError


class GlobLoader(object):
    def __init__(self, ctx: ContextConfig = None):
        self._ctx = ctx

    def init_ctx(self, ctx: ContextConfig):
        self._ctx = ctx

    def scan_dir(self, schema_dir: str):
        if self._ctx is None:
            raise ContextObjectNotSetError("Context was not set")

        if not schema_dir or not os.path.isdir(schema_dir):
            raise NotADirectoryError(f"Not a valid directory: {schema_dir}")

        schema_ext = self._ctx.schema_ext if self._ctx.schema_ext.startswith(".") else f".{self._ctx.schema_ext}"

        rex = re.compile(self._ctx.schema_pattern)

        file_items = []
        for _path in glob.glob(os.path.join(schema_dir, f"*{schema_ext}")):
            prefix, filename, extension = parse_file_path(_path)
            m = rex.match(filename + extension)
            if m:
                _ver, _seq, _name, _ext = m.groups()
            else:
                raise InvalidSchemaPatternError(f"Illegal file name: {_path}, does not match configured pattern")

            try:
                with open(_path, "r") as schema_file:
                    _content = schema_file.read()
            except Exception as err:
                raise InvalidSchemaFileError(f"Error reading file: {_path}, {str(err)}")

            file_items.append(
                ScriptData(version=_ver, sequence=_seq, name=_name, extension=_ext, path=_path, content=_content)
            )

        sorted_items = sorted(file_items, key=lambda k: (k.version_base, k.version_rank))
        return sorted_items
