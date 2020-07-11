# -*- coding: utf-8 -*-
import pytest

from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidSchemaPatternError, InvalidSchemaFileError
from esmigrate.internals import GlobLoader


@pytest.fixture(scope="module")
def glob_loader():
    """pytest fixture for providing default GlobLoader object"""
    _loader = GlobLoader()
    _loader.init_ctx(ContextConfig())
    return _loader


def test_scan_dir_raises_not_a_directory_error(glob_loader):
    """Test fails if scan_dir does not raise error for invalid directory"""
    with pytest.raises(NotADirectoryError):
        glob_loader.scan_dir("not_a_valid_path")


def test_scan_dir_parses_valid_file_names(glob_loader, fs):
    """Test fails if scan_dir cannot process a valid schema directory"""
    fs.create_file("./schema_dir/V1_1__create_index_mapping_for_twitter.exm")
    assert len(glob_loader.scan_dir("./schema_dir")) > 0


def test_scan_dir_raises_invalid_schema_file_error(glob_loader, fs):
    """Test fails if scan_dir dies not raise error when schema file cannot be read"""
    fs.create_file("./schema_dir/V1_1__create_index_mapping_for_twitter.exm", contents="dummy", st_size=10000)
    with pytest.raises(InvalidSchemaFileError):
        glob_loader.scan_dir("./schema_dir")


def test_scan_dir_raises_invalid_schema_pattern_error(glob_loader, fs):
    """Test fails if scan_dir does not raise error for invalid file names"""
    fs.create_file("./schema_dir/V1_1_create_index_mapping_for_twitter.exm")
    with pytest.raises(InvalidSchemaPatternError):
        glob_loader.scan_dir("./schema_dir")


def test_scan_dir_raises_context_object_not_set_error():
    """Test fails if scan_dir does not raise error when called without a context"""
    with pytest.raises(ContextObjectNotSetError):
        GlobLoader().scan_dir(".")
