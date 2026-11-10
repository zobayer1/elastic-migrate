import pytest
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.schema import CreateTable

from esmigrate.commons import MigVersion
from esmigrate.models import SCHEMA_TABLE, SchemaVersion


def create_table_sql(dialect):
    return str(CreateTable(SCHEMA_TABLE).compile(dialect=dialect))


def test_schema_version_is_stored_in_the_state_table():
    """Test fails if applied versions are not stored in esm_schema_state without a string version column"""
    assert SCHEMA_TABLE.name == "esm_schema_state"
    assert "version" not in SCHEMA_TABLE.columns


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect(), mysql.dialect()])
def test_schema_version_table_keys_are_namespaced_integer_versions(dialect):
    """Test fails if the table is not keyed by namespace and integer version with per-namespace installed rank"""
    sql = create_table_sql(dialect)
    assert "PRIMARY KEY (namespace, version_base, version_rank)" in sql
    assert "UNIQUE (namespace, installed_rank)" in sql
    assert "version_base INTEGER NOT NULL" in sql
    assert "version_rank INTEGER NOT NULL" in sql
    assert "AUTO_INCREMENT" not in sql
    assert "SERIAL" not in sql


@pytest.mark.parametrize(
    ("dialect", "fragments"),
    [
        (sqlite.dialect(), ["installed_on DATETIME", "query_results TEXT", "script VARCHAR(256)"]),
        (postgresql.dialect(), ["installed_on TIMESTAMP WITH TIME ZONE", "query_results TEXT", "checksum BYTEA"]),
        (mysql.dialect(), ["installed_on DATETIME(6)", "query_results LONGTEXT", "namespace VARCHAR(64) NOT NULL"]),
    ],
)
def test_schema_version_table_uses_portable_types(dialect, fragments):
    """Test fails if dialect-specific column types are not generated as expected"""
    sql = create_table_sql(dialect)
    for fragment in fragments:
        assert fragment in sql


def test_schema_version_version_is_read_only():
    """Test fails if the version can be reassigned instead of being derived from the integer columns"""
    scmver = SchemaVersion(version_base=1, version_rank=0)
    assert scmver.version == MigVersion(1, 0)
    with pytest.raises(AttributeError):
        scmver.version = MigVersion(2, 0)  # type: ignore[misc]
