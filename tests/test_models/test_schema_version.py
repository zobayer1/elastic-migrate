import getpass
from datetime import UTC

import pytest
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.schema import CreateTable

from esmigrate.commons import DEFAULT_NAMESPACE, Direction, Migration, MigVersion, ScriptData
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


def test_schema_version_defaults_to_default_namespace_and_utc_time():
    """Test fails if a new SchemaVersion is not in the default namespace with its version, user and UTC start time"""
    scmver = SchemaVersion(MigVersion(1, 10))
    assert scmver.namespace == DEFAULT_NAMESPACE
    assert (scmver.version, scmver.version_base, scmver.version_rank) == (MigVersion(1, 10), 1, 10)
    assert scmver.installed_by == getpass.getuser()
    assert scmver.type == "NOSQL"
    assert scmver.installed_on is not None
    assert scmver.installed_on.tzinfo == UTC


def test_schema_version_keeps_the_given_namespace():
    """Test fails if a SchemaVersion built for a namespace does not keep it"""
    assert SchemaVersion(MigVersion(1, 0), namespace="alpha").namespace == "alpha"


def test_schema_version_version_is_read_only():
    """Test fails if the version can be reassigned instead of being derived from the integer columns"""
    scmver = SchemaVersion(MigVersion(1, 0))
    with pytest.raises(AttributeError):
        scmver.version = MigVersion(2, 0)  # type: ignore[misc]


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
    assert (scmver.version, scmver.version_base, scmver.version_rank) == (MigVersion(1, 2), 1, 2)
    assert scmver.description == "create_index.esm"
    assert scmver.script == path
    assert scmver.checksum == script.checksum
    assert scmver.success is None


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
    assert (scmver.version, scmver.version_base, scmver.version_rank) == (MigVersion(1, 2), 1, 2)
    assert scmver.description == "create_index.esm"
    assert scmver.script is None
    assert scmver.checksum is None
