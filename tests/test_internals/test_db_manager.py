# -*- coding: utf-8 -*-
import pytest

from esmigrate.exceptions import InvalidDBConnectionError, SchemaVersionSqlDbError
from esmigrate.internals import get_db_manager
from esmigrate.models import SchemaVersion


@pytest.fixture(scope="module")
def db_manager():
    """pytest fixture for providing singleton DBManager instance"""
    _db_man = get_db_manager("sqlite:///:memory:", echo=True)
    return _db_man


@pytest.fixture(scope="function")
def db_with_success_row(db_manager):
    """pytest fixture for providing populated table with a single `success=true` entry"""
    scmver = SchemaVersion("1.0")
    scmver.success = True

    db_manager.insert_new_schema(scmver)
    yield db_manager
    db_manager.delete_all_schema()


@pytest.fixture(scope="function")
def db_with_failed_row(db_manager):
    """pytest fixture for providing populated table with a single `success=false` entry"""
    scmver = SchemaVersion("1.0")
    scmver.success = False

    db_manager.insert_new_schema(scmver)
    yield db_manager
    db_manager.delete_all_schema()


def test_db_manager_creates_table(db_manager):
    """Test fails if db_manager failed to create model during instantiation"""
    assert db_manager.schema_version_exists()


def test_db_manager_finds_by_version(db_with_success_row):
    """Test fails if find_schema_by_version cannot find entry with primary key `1.0`"""
    scmver_read = db_with_success_row.find_schema_by_version("1.0")
    assert scmver_read.version == "1.0"


def test_db_manager_finds_latest_schema(db_with_success_row):
    """Test fails if find_latest_schema cannot find latest schema"""
    row = db_with_success_row.find_latest_schema()
    assert row.installed_rank == 1


def test_db_manager_finds_all_schema(db_with_success_row):
    """Test fails if find_all_schema cannot find all records"""
    rows = db_with_success_row.find_all_schema()
    assert len(rows) == 1


def test_db_manager_inserts_schema_with_correct_installed_rank(db_with_success_row):
    """Test fails if insert_new_schema cannot assign next installed_rank"""
    scmver = SchemaVersion("1.1")
    scmver.success = True

    db_with_success_row.insert_new_schema(scmver)
    assert scmver.installed_rank == 2


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_db_manager_raises_error_when_inserting_duplicate(db_with_success_row):
    """Test fails if insert_new_schema does not fail integrity violation"""
    scmver = SchemaVersion("1.0")
    with pytest.raises(SchemaVersionSqlDbError):
        db_with_success_row.insert_new_schema(scmver)


def test_db_manager_raises_error_when_inserting_after_error(db_with_failed_row):
    """Test fails if insert_new_schema does not raise error when inserting after a failed row"""
    scmver = SchemaVersion("1.1")
    with pytest.raises(SchemaVersionSqlDbError):
        db_with_failed_row.insert_new_schema(scmver)


def test_db_manager_deletes_all_failed_schema(db_with_failed_row):
    """Test fails if delete_all_failed_schema does not remove the failed row"""
    db_with_failed_row.delete_all_failed_schema()
    rows = db_with_failed_row.find_all_schema()
    assert (len(rows)) == 0


def test_db_manager_cannot_find_entry(db_manager):
    """Test fails if find_schema_by_version does not return None for non existent key"""
    scmver_read = db_manager.find_schema_by_version("invalid_id")
    assert scmver_read is None


def test_db_manager_cannot_be_created_without_db_url():
    """Test fails if db_manager does not raise argument error for invalid db URL"""
    with pytest.raises(InvalidDBConnectionError):
        get_db_manager("invalid_db_url")
