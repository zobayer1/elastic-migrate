import re

import pytest

from esmigrate.exceptions import InvalidDBConnectionError
from esmigrate.internals import create_tables_sql
from esmigrate.internals.db_engine import to_async_url


@pytest.mark.parametrize(
    ("db_url", "expected"),
    [
        ("sqlite:///esmigrate.db", "sqlite+aiosqlite"),
        ("postgresql://user@host/db", "postgresql+asyncpg"),
        ("postgres://user@host/db", "postgresql+asyncpg"),
        ("mysql://user@host/db", "mysql+asyncmy"),
        ("mariadb://user@host/db", "mysql+asyncmy"),
        ("postgresql+psycopg://user@host/db", "postgresql+psycopg"),
    ],
)
def test_to_async_url_selects_async_driver(db_url, expected):
    """Test fails if to_async_url does not map bare dialects to async drivers or keeps explicit drivers"""
    assert to_async_url(db_url).drivername == expected


@pytest.mark.parametrize("db_url", ["invalid_db_url", "oracle://user@host/db"])
def test_to_async_url_rejects_invalid_or_unsupported_urls(db_url):
    """Test fails if to_async_url accepts malformed URLs or unsupported databases"""
    with pytest.raises(InvalidDBConnectionError):
        to_async_url(db_url)


def statements(sql):
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


@pytest.mark.parametrize(
    ("db_url", "schema", "prefix"),
    [
        ("sqlite:///esmigrate.db", None, ""),
        ("postgresql://user@host/db", None, ""),
        ("postgresql://user@host/db", "esm", "esm."),
        ("mysql://user@host/db", None, ""),
        ("mysql://user@host/db", "esm", "esm."),
        ("mariadb://user@host/db", "esm", "esm."),
    ],
)
def test_create_tables_sql_prints_both_tables_and_the_index(db_url, schema, prefix):
    """Test fails if the printed SQL is not the two tables and the history index, qualified with the schema"""
    sql = create_tables_sql(db_url, schema)
    parts = statements(sql)
    assert sql.endswith(";")
    assert [re.sub(r"\s*\(.*", "", part, flags=re.S) for part in parts] == [
        f"CREATE TABLE {prefix}esm_schema_state",
        f"CREATE TABLE {prefix}esm_schema_history",
        f"CREATE INDEX ix_esm_schema_history_namespace_id ON {prefix}esm_schema_history",
    ]
    assert "esm_schema_lock" not in sql


@pytest.mark.parametrize("db_url", ["invalid_db_url", "oracle://user@host/db", "postgresql+nosuch://user@host/db"])
def test_create_tables_sql_rejects_invalid_urls_and_drivers(db_url):
    """Test fails if SQL is printed for a URL or driver that a normal run would refuse"""
    with pytest.raises(InvalidDBConnectionError):
        create_tables_sql(db_url)


def test_create_tables_sql_does_not_connect(tmp_path):
    """Test fails if printing the SQL opens the database"""
    create_tables_sql(f"sqlite:///{tmp_path / 'never.db'}")
    assert not (tmp_path / "never.db").exists()
