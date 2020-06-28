# -*- coding: utf-8 -*-
import os
import re

import pytest

from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidSchemaPatternError
from esmigrate.internals import GlobLoader


@pytest.fixture(scope='module')
def loader():
    _context = ContextConfig().load_for('test')
    _loader = GlobLoader()
    _loader.init_ctx(_context)
    return _loader


def test_glob_loader_initialized_with_test_context(loader):
    assert loader.get_ctx().profile == 'test'


def test_scan_dir_raises_not_a_directory_error(loader):
    with pytest.raises(NotADirectoryError):
        loader.scan_dir('not_a_valid_path')


def test_scan_dir_parses_valid_file_names(loader):
    assert len(loader.scan_dir('tests/resources/schema_dir')) > 0


@pytest.fixture(scope='function')
def params(request):
    return request.param


@pytest.mark.parametrize('params', [
    'V1_1__create_index_mapping_for_twitter.exm',
    'V1_2__create_new_doc_in_twitter.exm',
    'V1_3__update_existing_doc_in_twitter.exm',
    'V1_3__update_existing_doc_in_twitter.exm',
    'V1_4__delete_all_doc_in_twitter.exm',
    'V1_5__delete_index_twitter.exm',
], indirect=True)
def test_envvar_regex(monkeypatch, params):
    monkeypatch.setenv('SCHEMA_PATTERN',
                       'V(?P<version>[\\d]+)_(?P<sequence>[\\d]+)__(?P<name>[\\w]+)\\.(?P<extension>[\\w]+)')

    _context = ContextConfig()
    _pattern = rf"^{os.getenv('SCHEMA_PATTERN')}$"
    assert _context.schema_pattern == _pattern

    rex = re.compile(_pattern)
    assert rex.match(params)


def test_scan_dir_raises_invalid_schema_pattern_error():
    _ctx = ContextConfig()
    _ctx.schema_pattern = \
        r'^(?P<version>[\d]+)_(?P<sequence>[\d]+)_(?P<name>[\w]+)\.(?P<extension>[\w]+)$'
    with pytest.raises(InvalidSchemaPatternError):
        GlobLoader(_ctx).scan_dir('tests/resources/schema_dir')


def test_scan_dir_raises_context_object_not_set_error():
    with pytest.raises(ContextObjectNotSetError):
        GlobLoader().scan_dir('.')
