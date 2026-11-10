import sqlite3
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import OperationalError

from esmigrate.commons import MigVersion
from esmigrate.exceptions import LegacySchemaTableError, SchemaVersionSqlDbError
from esmigrate.internals import LEGACY_TABLE, DBManager, Layout
from esmigrate.internals.legacy_layout import old_timestamp_to_utc
from tests.test_internals.db_helpers import execute, history_rows, query, record, sqlite_path, state_rows, table_names

V1_TABLE_DDL = """
CREATE TABLE esm_schema_version (
    version VARCHAR NOT NULL PRIMARY KEY,
    version_base INTEGER,
    version_rank INTEGER,
    installed_rank INTEGER UNIQUE,
    description VARCHAR,
    type VARCHAR,
    script VARCHAR,
    checksum BLOB,
    installed_by VARCHAR,
    installed_on DATETIME,
    execution_time INTEGER,
    success BOOLEAN,
    query_results VARCHAR
)
"""

V2_TABLE_DDL = """
CREATE TABLE esm_schema_version (
    namespace VARCHAR(64) NOT NULL,
    version VARCHAR(64) NOT NULL,
    version_base INTEGER,
    version_rank INTEGER,
    installed_rank INTEGER,
    description VARCHAR(255),
    type VARCHAR(16),
    script VARCHAR(1024),
    checksum BLOB,
    installed_by VARCHAR(255),
    installed_on DATETIME,
    execution_time INTEGER,
    success BOOLEAN,
    query_results TEXT,
    PRIMARY KEY (namespace, version),
    UNIQUE (namespace, installed_rank)
)
"""

V1_ROWS = [
    (
        "1.0",
        9,
        9,
        1,
        "a.esm",
        "NOSQL",
        "/srv/schema/V1_0__a.esm",
        b"x",
        "ops",
        "2021-06-16 09:57:22.123456",
        1,
        1,
        "r1",
    ),
    ("1.1", 9, 9, 2, "b.esm", "NOSQL", "C:\\schema\\V1_1__b.esm", b"y", "ops", "2021-06-17 10:00:00", 2, 0, "r2"),
    ("1.2", 9, 9, 3, "c.esm", "NOSQL", None, None, "ops", None, None, None, None),
]

V2_ROWS = [
    ("beta", "2.0", 9, 9, 1, "c.esm", "NOSQL", "V2_0__c.esm", b"z", "ci", "2021-06-18 08:00:00.000000", 4, 1, "r3"),
    (
        "alpha",
        "1.1",
        9,
        9,
        2,
        "b.esm",
        "NOSQL",
        "V1_1__b.esm",
        b"y",
        "ops",
        "2021-06-17 10:00:00.000000",
        None,
        0,
        "r2",
    ),
    ("alpha", "1.0", 9, 9, 1, "a.esm", "NOSQL", "V1_0__a.esm", b"x", "ops", "2021-06-16 09:57:22.123456", 1, 1, "r1"),
    ("beta", "2.1", 9, 9, None, "d.esm", "NOSQL", "V2_1__d.esm", None, "ci", None, 0, 1, None),
]


def create_old_table(db_url, ddl, rows):
    execute(db_url, ddl)
    with sqlite3.connect(sqlite_path(db_url)) as conn:
        conn.executemany(f"INSERT INTO esm_schema_version VALUES ({', '.join('?' * len(rows[0]))})", rows)
    conn.close()


@pytest.mark.parametrize(("ddl", "rows", "layout"), [(V1_TABLE_DDL, V1_ROWS, "V1"), (V2_TABLE_DDL, V2_ROWS, "V2")])
async def test_db_manager_refuses_old_layout_without_upgrade(db_url, ddl, rows, layout):
    """Test fails if a v1 or v2 table with rows is not refused, without changes, unless init asks for the copy"""
    create_old_table(db_url, ddl, rows)
    with pytest.raises(LegacySchemaTableError, match=f"use the {layout} layout, run `esmigrate init`"):
        async with DBManager.connect(db_url):
            pass
    assert table_names(db_url) == {LEGACY_TABLE}


@pytest.mark.parametrize("ddl", [V1_TABLE_DDL, V2_TABLE_DDL])
async def test_db_manager_treats_empty_old_table_as_current(db_url, ddl):
    """Test fails if an empty v1 or v2 table blocks commands or is changed"""
    execute(db_url, ddl)
    async with DBManager.connect(db_url) as db:
        assert db.upgraded_from is Layout.CURRENT
        await record(db)
    assert query(db_url, "SELECT count(*) FROM esm_schema_version") == [(0,)]


async def test_db_manager_copies_v1_rows(db_url):
    """Test fails if v1 rows are not copied into the default namespace with file names, milliseconds and UTC times"""
    create_old_table(db_url, V1_TABLE_DDL, V1_ROWS)
    async with DBManager.connect(db_url, upgrade=True) as db:
        assert db.upgraded_from is Layout.V1
        rows = await db.find_all_schema()
        history = await db.find_history()
    assert [(row.namespace, row.version, row.installed_rank) for row in rows] == [
        ("default", MigVersion(1, 0), 1),
        ("default", MigVersion(1, 1), 2),
        ("default", MigVersion(1, 2), 3),
    ]
    assert [row.script for row in rows] == ["V1_0__a.esm", "V1_1__b.esm", None]
    assert [row.success for row in rows] == [True, False, None]
    assert [row.execution_time for row in rows] == [1000, 2000, None]
    assert [row.checksum for row in rows] == [b"x", b"y", None]
    assert [row.installed_on for row in rows] == [
        datetime(2021, 6, 16, 9, 57, 22, 123456).astimezone(UTC),
        datetime(2021, 6, 17, 10, 0).astimezone(UTC),
        None,
    ]
    assert [(entry.operation, entry.version_base, entry.version_rank) for entry in history] == [
        ("up", 1, 0),
        ("up", 1, 1),
        ("up", 1, 2),
    ]
    first, row = history[0], rows[0]
    assert (first.description, first.script, first.checksum) == (row.description, row.script, row.checksum)
    assert (first.executed_by, first.executed_on) == (row.installed_by, row.installed_on)
    assert (first.execution_time, first.success, first.query_results) == (1000, True, "r1")
    assert query(db_url, "SELECT version FROM esm_schema_version ORDER BY version") == [("1.0",), ("1.1",), ("1.2",)]


@pytest.mark.usefixtures("local_time_plus_six")
async def test_db_manager_copies_v2_rows(db_url):
    """Test fails if v2 rows lose their namespace or script, or their UTC times are shifted"""
    create_old_table(db_url, V2_TABLE_DDL, V2_ROWS)
    async with DBManager.connect(db_url, upgrade=True, namespace="alpha") as db:
        assert db.upgraded_from is Layout.V2
        alpha = await db.find_all_schema()
    assert [(row.version, row.script, row.success, row.execution_time) for row in alpha] == [
        (MigVersion(1, 0), "V1_0__a.esm", True, 1000),
        (MigVersion(1, 1), "V1_1__b.esm", False, None),
    ]
    assert alpha[0].installed_on == datetime(2021, 6, 16, 9, 57, 22, 123456, tzinfo=UTC)
    assert history_rows(db_url) == [
        ("alpha", 1, 0, "up", 1, 1000, "r1"),
        ("alpha", 1, 1, "up", 0, None, "r2"),
        ("beta", 2, 1, "up", 1, 0, None),
        ("beta", 2, 0, "up", 1, 4000, "r3"),
    ]


async def test_db_manager_copies_old_rows_only_once(db_url):
    """Test fails if a second init or a reset after the upgrade copies the old rows again"""
    create_old_table(db_url, V2_TABLE_DDL, V2_ROWS)
    async with DBManager.connect(db_url, upgrade=True, namespace="alpha"):
        pass
    async with DBManager.connect(db_url, upgrade=True, namespace="alpha") as db:
        assert db.upgraded_from is Layout.CURRENT
        await db.delete_all_schema()
    async with DBManager.connect(db_url, upgrade=True, namespace="alpha") as db:
        assert db.upgraded_from is Layout.CURRENT
        assert await db.find_all_schema() == []
    assert len(history_rows(db_url)) == len(V2_ROWS)


async def test_db_manager_copies_old_rows_in_configured_schema(db_url):
    """Test fails if the copy does not read the old table from the configured schema"""
    create_old_table(db_url, V1_TABLE_DDL, V1_ROWS)
    async with DBManager.connect(db_url, upgrade=True, schema="main") as db:
        assert db.upgraded_from is Layout.V1
        assert len(await db.find_all_schema()) == len(V1_ROWS)


async def test_db_manager_refuses_copy_of_unusable_versions(db_url):
    """Test fails if unparseable, out-of-range or colliding versions are not all listed before anything is copied"""
    row = ("NOSQL", "V.esm", None, "ops", None, 1, 1, None)
    rows = [
        ("default", "1.01", 1, 0, 1, "a.esm", *row),
        ("other", "1.01", 1, 0, 1, "a.esm", *row),
        ("default", "1.1", 1, 1, 2, "b.esm", *row),
        ("default", "abc", 1, 2, 3, "c.esm", *row),
        ("default", "99999999999.0", 1, 3, 4, "d.esm", *row),
    ]
    create_old_table(db_url, V2_TABLE_DDL, rows)
    with pytest.raises(SchemaVersionSqlDbError) as raised:
        async with DBManager.connect(db_url, upgrade=True):
            pass
    assert str(raised.value) == (
        "Cannot copy existing schema versions:\n"
        "  default: 1.01 and 1.1 are the same version\n"
        "  default: Schema version 99999999999.0 is out of range: [0, 2147483647]\n"
        "  default: Invalid version: abc"
    )
    assert state_rows(db_url) == []
    assert history_rows(db_url) == []
    assert query(db_url, "SELECT count(*) FROM esm_schema_version") == [(5,)]


async def test_db_manager_wraps_copy_errors(db_url, mocker):
    """Test fails if database errors during the copy are not raised as SchemaVersionSqlDbError"""
    create_old_table(db_url, V1_TABLE_DDL, V1_ROWS)
    error = OperationalError("INSERT", {}, Exception("disk I/O error"))
    mocker.patch("esmigrate.internals.db_manager.copy_old_rows", side_effect=error)
    with pytest.raises(SchemaVersionSqlDbError, match="Copying existing schema versions failed"):
        async with DBManager.connect(db_url, upgrade=True):
            pass


def test_old_timestamp_to_utc_keeps_missing_timestamps():
    """Test fails if a missing timestamp gets a fabricated value"""
    assert old_timestamp_to_utc(None) is None


def test_old_timestamp_to_utc_converts_aware_timestamps():
    """Test fails if a timestamp with a time zone is not converted to UTC"""
    aware = datetime(2021, 6, 16, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    assert old_timestamp_to_utc(aware, force_utc=True) == datetime(2021, 6, 16, 10, 0, tzinfo=UTC)


@pytest.mark.usefixtures("local_time_plus_six")
@pytest.mark.parametrize(
    ("value", "force_utc", "expected"),
    [
        (datetime(2021, 6, 16, 12, 0), False, datetime(2021, 6, 16, 6, 0, tzinfo=UTC)),
        (datetime(2021, 6, 16, 12, 0), True, datetime(2021, 6, 16, 12, 0, tzinfo=UTC)),
        ("2021-06-16 12:00:00.123456", False, datetime(2021, 6, 16, 6, 0, 0, 123456, tzinfo=UTC)),
        ("2021-06-16 12:00:00.123456", True, datetime(2021, 6, 16, 12, 0, 0, 123456, tzinfo=UTC)),
    ],
)
def test_old_timestamp_to_utc_reads_naive_timestamps_as_local_or_utc(value, force_utc, expected):
    """Test fails if naive v1 timestamps are not read as local time or naive v2 timestamps are shifted"""
    result = old_timestamp_to_utc(value, force_utc)
    assert result == expected
    assert result is not None
    assert result.tzinfo == UTC
