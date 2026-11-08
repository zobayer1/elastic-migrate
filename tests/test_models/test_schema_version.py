from datetime import UTC

import pytest
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.schema import CreateTable

from esmigrate.commons import DEFAULT_NAMESPACE, Direction, Migration, MigVersion, ScriptData
from esmigrate.internals.db_manager import SCHEMA_TABLE
from esmigrate.models import SchemaVersion


def create_table_sql(dialect):
    return str(CreateTable(SCHEMA_TABLE).compile(dialect=dialect))


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
    assert scmver.installed_on is not None
    assert scmver.installed_on.tzinfo == UTC


def make_script(path, direction, content="GET twitter"):
    return ScriptData(MigVersion(1, 2), "create_index", "esm", path, content, direction)


@pytest.mark.parametrize(
    ("path", "direction"),
    [("V1_2__create_index.esm", None), ("V1_2__create_index.up.esm", Direction.UP)],
)
def test_schema_version_is_created_from_migration_with_up_script(path, direction):
    """Test fails if from_migration does not copy the version, description, path and checksum of the up script"""
    script = make_script(path, direction)
    scmver = SchemaVersion.from_migration(Migration(up=script))
    assert (scmver.version, scmver.version_base, scmver.version_rank) == ("1.2", 1, 2)
    assert scmver.description == "create_index.esm"
    assert scmver.script == path
    assert scmver.checksum == script.checksum


def test_schema_version_records_up_script_of_a_pair():
    """Test fails if from_migration records the down script of a reversible migration"""
    up = make_script("V1_2__create_index.up.esm", Direction.UP, content="PUT twitter")
    down = make_script("V1_2__create_index.down.esm", Direction.DOWN, content="DELETE twitter")
    scmver = SchemaVersion.from_migration(Migration(up=up, down=down))
    assert scmver.script == "V1_2__create_index.up.esm"
    assert scmver.checksum == up.checksum


def test_schema_version_leaves_script_empty_for_down_only_migration():
    """Test fails if a down-only migration does not keep its version and description with no script or checksum"""
    down = make_script("V1_2__create_index.down.esm", Direction.DOWN)
    scmver = SchemaVersion.from_migration(Migration(down=down))
    assert (scmver.version, scmver.version_base, scmver.version_rank) == ("1.2", 1, 2)
    assert scmver.description == "create_index.esm"
    assert scmver.script is None
    assert scmver.checksum is None
