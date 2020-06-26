# -*- coding: utf-8 -*-
import glob
import os
import re

from esmigrate.commons import parse_file_path
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidSchemaPatternError


class GlobLoader(object):

    def __init__(self, ctx: ContextConfig = None):
        self._ctx = ctx

    def init_ctx(self, ctx: ContextConfig):
        self._ctx = ctx

    def get_ctx(self):
        return self._ctx

    def scan_dir(self):
        if self._ctx is None:
            raise ContextObjectNotSetError('Context not set')

        if self._ctx.schema_dir:
            if os.path.isabs(self._ctx.schema_dir):
                _schema_dir = self._ctx.schema_dir
            else:
                _schema_dir = os.path.join(os.getcwd(), self._ctx.schema_dir)
        else:
            _schema_dir = os.getcwd()

        if not os.path.isdir(_schema_dir):
            raise NotADirectoryError(f'Not a valid directory: {_schema_dir}')

        _schema_ext = self._ctx.schema_ext if self._ctx.schema_ext.startswith('.') else f'.{self._ctx.schema_ext}'

        rex = re.compile(self._ctx.schema_pattern)

        file_items = []
        for _item in glob.glob(os.path.join(_schema_dir, f'*{_schema_ext}')):
            prefix, filename, extension = parse_file_path(_item)
            _match = rex.match(filename + extension)
            if _match:
                _ver, _seq, _name, _ext = _match.groups()
            else:
                raise InvalidSchemaPatternError(f'Illegal file name: {_item}, does not match configured pattern')
            file_items.append(_item)

        return file_items
