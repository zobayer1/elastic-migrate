import pytest
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from esmigrate.internals.db_manager import HISTORY_TABLE
from esmigrate.models import SchemaHistory


def create_table_sql(dialect):
    return str(CreateTable(HISTORY_TABLE).compile(dialect=dialect))


def test_schema_history_is_stored_in_its_own_table():
    """Test fails if the history table or its columns differ from the documented layout"""
    assert SchemaHistory.__tablename__ == "esm_schema_history"
    assert [column.name for column in HISTORY_TABLE.columns] == [
        "id",
        "namespace",
        "version_base",
        "version_rank",
        "operation",
        "description",
        "script",
        "checksum",
        "executed_by",
        "executed_on",
        "execution_time",
        "success",
        "query_results",
    ]


@pytest.mark.parametrize(
    ("dialect", "identity"),
    [
        (sqlite.dialect(), "id INTEGER NOT NULL"),
        (postgresql.dialect(), "id SERIAL NOT NULL"),
        (mysql.dialect(), "id INTEGER NOT NULL AUTO_INCREMENT"),
    ],
)
def test_schema_history_rows_are_keyed_by_an_autoincrement_id(dialect, identity):
    """Test fails if history rows are not keyed by a generated id that gives the event order"""
    sql = create_table_sql(dialect)
    assert identity in sql
    assert "PRIMARY KEY (id)" in sql


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect(), mysql.dialect()])
def test_schema_history_requires_namespace_and_operation_only(dialect):
    """Test fails if namespace and operation may be empty or the version may not be, as reset rows need"""
    sql = create_table_sql(dialect)
    assert "namespace VARCHAR(64) NOT NULL" in sql
    assert "operation VARCHAR(8) NOT NULL" in sql
    assert "version_base INTEGER," in sql
    assert "version_rank INTEGER," in sql


@pytest.mark.parametrize(
    ("dialect", "fragments"),
    [
        (sqlite.dialect(), ["executed_on DATETIME", "query_results TEXT", "checksum BLOB"]),
        (postgresql.dialect(), ["executed_on TIMESTAMP WITH TIME ZONE", "query_results TEXT", "checksum BYTEA"]),
        (mysql.dialect(), ["executed_on DATETIME(6)", "query_results LONGTEXT", "checksum BLOB"]),
    ],
)
def test_schema_history_table_uses_portable_types(dialect, fragments):
    """Test fails if dialect-specific column types are not generated as expected"""
    sql = create_table_sql(dialect)
    for fragment in fragments:
        assert fragment in sql


def test_schema_history_is_indexed_by_namespace_then_id():
    """Test fails if the history index cannot serve per-namespace lookups in event order"""
    (index,) = HISTORY_TABLE.indexes
    assert str(CreateIndex(index).compile(dialect=sqlite.dialect())) == (
        "CREATE INDEX ix_esm_schema_history_namespace_id ON esm_schema_history (namespace, id)"
    )
