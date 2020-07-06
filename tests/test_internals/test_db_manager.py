# -*- coding: utf-8 -*-
import pytest

from esmigrate.exceptions import InvalidDBConnectionError, InvalidSchemaVersionError
from esmigrate.internals import get_db_manager
from esmigrate.models import SchemaVersion


@pytest.fixture(scope="session")
def db_manager():
    """pytest fixture for providing singleton DBManager instance"""
    _db_man = get_db_manager("sqlite:///:memory:", echo=True)
    _db_man.initialize_db()
    return _db_man


@pytest.mark.dependency()
def test_db_manager_successfully_creates_an_entry(db_manager):
    """Test fails if insert_new_schema fails with an error"""
    scmver = SchemaVersion("v1.0")
    db_manager.insert_new_schema(scmver)


@pytest.mark.dependency(depends=["test_db_manager_successfully_creates_an_entry"])
def test_db_manager_successfully_finds_created_object(db_manager):
    """Test fails if find_schema_by_version cannot find entry with key `v1.0`"""
    scmver_read = db_manager.find_schema_by_version("v1.0")
    assert scmver_read.version == "v1.0"


@pytest.mark.dependency(
    depends=["test_db_manager_successfully_creates_an_entry", "test_db_manager_successfully_finds_created_object"]
)
def test_db_manager_raises_error_when_inserting_duplicate(db_manager):
    """Test fails if insert_new_schema does not fail integrity violation"""
    scmver = SchemaVersion("v1.0")
    with pytest.raises(InvalidSchemaVersionError):
        db_manager.insert_new_schema(scmver)


def test_db_manager_cannot_find_entry(db_manager):
    """Test fails if find_schema_by_version does not return None for non existent key"""
    scmver_read = db_manager.find_schema_by_version("invalid_id")
    assert scmver_read is None


def test_db_manager_cannot_be_created_without_db_url():
    """Test fails if db_manager does not raise argument error for invalid db URL"""
    with pytest.raises(InvalidDBConnectionError):
        get_db_manager("invalid_db_url")
