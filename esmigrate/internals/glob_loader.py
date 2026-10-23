import glob
import os
import re

from esmigrate.commons import ScriptData, parse_file_path
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidSchemaFileError, InvalidSchemaPatternError

MAX_VERSION_PART = 2**31 - 1


class GlobLoader:
    def __init__(self, ctx: ContextConfig | None = None) -> None:
        self._ctx = ctx

    def init_ctx(self, ctx: ContextConfig) -> None:
        self._ctx = ctx

    def scan_dir(self, schema_dir: str) -> list[ScriptData]:
        if self._ctx is None:
            raise ContextObjectNotSetError("Context was not set")

        if not schema_dir or not os.path.isdir(schema_dir):
            raise NotADirectoryError(f"Not a valid directory: {schema_dir}")

        schema_ext = self._ctx.schema_ext if self._ctx.schema_ext.startswith(".") else f".{self._ctx.schema_ext}"

        rex = re.compile(self._ctx.schema_pattern)

        file_items: list[ScriptData] = []
        for _path in glob.glob(os.path.join(schema_dir, f"*{schema_ext}")):
            _, filename, extension = parse_file_path(_path)
            m = rex.match(filename + extension)
            if m:
                _ver, _seq, _name, _ext = m.groups()
            else:
                raise InvalidSchemaPatternError(f"Illegal file name: {_path}, does not match configured pattern")
            if max(int(_ver), int(_seq)) > MAX_VERSION_PART:
                raise InvalidSchemaPatternError(f"Version number too large: {_path}, maximum is {MAX_VERSION_PART}")

            try:
                with open(_path, encoding="utf-8") as schema_file:
                    _content = schema_file.read()
            except Exception as err:
                raise InvalidSchemaFileError(f"Error reading file: {_path}, {err!s}") from err

            file_items.append(
                ScriptData(
                    version=_ver,
                    sequence=_seq,
                    name=_name,
                    extension=_ext,
                    path=os.path.relpath(_path, schema_dir),
                    content=_content,
                )
            )

        sorted_items = sorted(file_items, key=lambda k: k.version_key)
        return sorted_items
