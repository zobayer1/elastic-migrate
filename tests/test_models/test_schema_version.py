from datetime import UTC

import pytest
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.schema import CreateTable

from esmigrate.commons import DEFAULT_NAMESPACE, ScriptData
from esmigrate.models import SchemaVersion


def create_table_sql(dialect):
    return str(CreateTable(SchemaVersion.__table__).compile(dialect=dialect))


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect(), mysql.dialect()])
def test_schema_version_table_keys_are_namespaced(dialect):
    """Test fails if the table is not keyed by namespace and version with per-namespace installed rank"""
    sql = create_table_sql(dialect)
    assert "PRIMARY KEY (namespace, version)" in sql
    assert "UNIQUE (namespace, installed_rank)" in sql


@pytest.mark.parametrize(
    ("dialect", "fragments"),
    [
        (sqlite.dialect(), ["installed_on DATETIME", "query_results TEXT"]),
        (postgresql.dialect(), ["installed_on TIMESTAMP WITH TIME ZONE", "query_results TEXT", "checksum BYTEA"]),
        (mysql.dialect(), ["installed_on DATETIME(6)", "query_results LONGTEXT", "version VARCHAR(64) NOT NULL"]),
    ],
)
def test_schema_version_table_uses_portable_types(dialect, fragments):
    """Test fails if dialect-specific column types are not generated as expected"""
    sql = create_table_sql(dialect)
    for fragment in fragments:
        assert fragment in sql


def test_schema_version_defaults_to_default_namespace_and_utc_time():
    """Test fails if a new SchemaVersion is not in the default namespace with a UTC-aware install time"""
    scmver = SchemaVersion("1.0")
    assert scmver.namespace == DEFAULT_NAMESPACE
    assert scmver.installed_on.tzinfo == UTC


def test_schema_version_is_created_from_script_data():
    """Test fails if from_script_data does not copy version, description, path and checksum"""
    script_data = ScriptData("1", "2", "create_index", "exm", "V1_2__create_index.exm", "GET twitter")
    scmver = SchemaVersion.from_script_data(script_data)
    assert (scmver.version, scmver.version_base, scmver.version_rank) == ("1.2", 1, 2)
    assert scmver.description == "create_index.exm"
    assert scmver.script == "V1_2__create_index.exm"
    assert scmver.checksum == script_data.checksum
