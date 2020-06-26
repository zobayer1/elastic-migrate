# -*- coding: utf-8 -*-
import os
import re

import pytest

from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError
from esmigrate.internals import GlobLoader


@pytest.fixture(scope='module')
def context():
    return ContextConfig().load_for('dev')


@pytest.fixture(scope='module')
def loader(context):
    _loader = GlobLoader()
    _loader.init_ctx(context)
    return _loader


def test_scan_dir_raises_context_not_set_error():
    with pytest.raises(ContextObjectNotSetError):
        GlobLoader().scan_dir()


def test_scan_dir_initialized(loader):
    assert loader.get_ctx().profile == 'dev'


def test_scan_dir_loads_absolute_path(loader):
    loader.get_ctx().schema_dir = os.path.join(os.getcwd(), 'tests', 'resources', 'schema_dir')
    assert len(loader.scan_dir()) >= 0


def test_scan_dir_loads_relative_path(loader):
    loader.get_ctx().schema_dir = 'tests/resources/schema_dir'
    assert len(loader.scan_dir()) >= 0


def test_scan_dir_loads_current_working_dir(loader):
    loader.get_ctx().schema_dir = None
    assert len(loader.scan_dir()) >= 0


def test_scan_dir_raises_not_a_directory_error(loader):
    loader.get_ctx().schema_dir = 'wtf'
    with pytest.raises(NotADirectoryError):
        loader.scan_dir()


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
def test_envvar_regex(monkeypatch, context, params):
    monkeypatch.setenv('SCHEMA_PATTERN',
                       'V(?P<version>[\\d]+)_(?P<sequence>[\\d]+)__(?P<name>[\\w]+)\\.(?P<extension>[\\w]+)')
    pattern = rf"^{os.getenv('SCHEMA_PATTERN')}$"
    # test that envvar can be read
    assert context.schema_pattern == pattern
    # test that envvar overwrites default assignment
    context2 = ContextConfig()
    assert context2.schema_pattern == pattern

    rex = re.compile(pattern)
    assert rex.match(params)
