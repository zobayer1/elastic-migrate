# -*- coding: utf-8 -*-
import pytest

from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidSchemaPatternError
from esmigrate.internals import GlobLoader


@pytest.fixture(scope="module")
def glob_loader():
    _loader = GlobLoader()
    _loader.init_ctx(ContextConfig())
    return _loader


def test_scan_dir_raises_not_a_directory_error(glob_loader):
    with pytest.raises(NotADirectoryError):
        glob_loader.scan_dir("not_a_valid_path")


def test_scan_dir_parses_valid_file_names(glob_loader, fs):
    fs.create_file("./schema_dir/V1_1__create_index_mapping_for_twitter.exm")
    assert len(glob_loader.scan_dir("./schema_dir")) > 0


def test_scan_dir_raises_invalid_schema_pattern_error(glob_loader, fs):
    fs.create_file("./schema_dir/V1_1_create_index_mapping_for_twitter.exm")
    with pytest.raises(InvalidSchemaPatternError):
        glob_loader.scan_dir("./schema_dir")


def test_scan_dir_raises_context_object_not_set_error():
    with pytest.raises(ContextObjectNotSetError):
        GlobLoader().scan_dir(".")
