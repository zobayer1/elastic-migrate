import asyncio
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import make_url, text

from esmigrate.exceptions import Errors
from esmigrate.internals import LEGACY_TABLE
from esmigrate.internals.db_manager import create_engine
from tests.integration.test_migrations import BULK_DOCUMENTS, CREATE_INDEX, INDEX_DOCUMENT, doc_count, write_schemas

V1_TYPES = {
    "sqlite": {"binary": "BLOB", "timestamp": "DATETIME"},
    "postgresql": {"binary": "BYTEA", "timestamp": "TIMESTAMP WITHOUT TIME ZONE"},
}
V2_TYPES = {
    "sqlite": {"binary": "BLOB", "timestamp": "DATETIME", "boolean": "BOOLEAN", "text": "TEXT"},
    "postgresql": {"binary": "BYTEA", "timestamp": "TIMESTAMP WITH TIME ZONE", "boolean": "BOOLEAN", "text": "TEXT"},
    "mysql": {"binary": "BLOB", "timestamp": "DATETIME(6)", "boolean": "BOOL", "text": "LONGTEXT"},
}
V1_INSTALLED_ON = [datetime(2021, 6, 16, 9, 57, 22, 123456), datetime(2021, 6, 17, 10, 0, 0)]
V1_SCRIPTS = ["V1_0__create_index.esm", "V1_1__index_document.esm"]
V2_INSTALLED_ON = datetime(2021, 6, 16, 9, 57, 22, 123456, tzinfo=UTC)


def v1_table_ddl(dialect):
    types = V1_TYPES[dialect]
    return (
        "CREATE TABLE esm_schema_version (version VARCHAR NOT NULL, version_base INTEGER, version_rank INTEGER, "
        f"installed_rank INTEGER, description VARCHAR, type VARCHAR, script VARCHAR, checksum {types['binary']}, "
        f"installed_by VARCHAR, installed_on {types['timestamp']}, execution_time INTEGER, success BOOLEAN, "
        "query_results VARCHAR, PRIMARY KEY (version), UNIQUE (installed_rank))"
    )


def v2_table_ddl(dialect):
    types = V2_TYPES[dialect]
    return (
        "CREATE TABLE esm_schema_version (namespace VARCHAR(64) NOT NULL, version VARCHAR(64) NOT NULL, "
        "version_base INTEGER, version_rank INTEGER, installed_rank INTEGER, description VARCHAR(255), "
        f"type VARCHAR(16), script VARCHAR(1024), checksum {types['binary']}, installed_by VARCHAR(255), "
        f"installed_on {types['timestamp']}, execution_time INTEGER, success {types['boolean']}, "
        f"query_results {types['text']}, PRIMARY KEY (namespace, version), UNIQUE (namespace, installed_rank))"
    )


async def execute(db_url, *statements):
    engine = create_engine(db_url)
    try:
        async with engine.begin() as conn:
            results = [await conn.execute(text(sql), params) for sql, params in statements]
            return [result.all() if result.returns_rows else None for result in results]
    finally:
        await engine.dispose()


def count_rows(db_url, table):
    (rows,) = asyncio.run(execute(db_url, (f"SELECT count(*) FROM {table}", {})))
    assert rows is not None
    return rows[0][0]


def create_v1_installation(db_url):
    dialect = make_url(db_url).get_backend_name()
    rows = []
    for rank, (script, installed_on) in enumerate(zip(V1_SCRIPTS, V1_INSTALLED_ON, strict=True), start=1):
        rows.append(
            (
                "INSERT INTO esm_schema_version VALUES "
                "(:version, 1, :rank_minus_one, :rank, :description, 'NOSQL', :script, :checksum, 'ops', "
                ":installed_on, 1, :success, '[]')",
                {
                    "version": f"1.{rank - 1}",
                    "rank_minus_one": rank - 1,
                    "rank": rank,
                    "description": script.split("__", 1)[1],
                    "script": f"/srv/project/schema_dir/{script}",
                    "checksum": f"sha1-{rank}".encode(),
                    "installed_on": installed_on if dialect == "postgresql" else installed_on.isoformat(" "),
                    "success": True,
                },
            )
        )
    asyncio.run(execute(db_url, (v1_table_ddl(dialect), {}), *rows))


def create_v2_installation(db_url, rows):
    dialect = make_url(db_url).get_backend_name()
    installed_on = {
        "postgresql": V2_INSTALLED_ON,
        "mysql": V2_INSTALLED_ON.replace(tzinfo=None),
        "sqlite": V2_INSTALLED_ON.replace(tzinfo=None).isoformat(" "),
    }[dialect]
    inserts = [
        (
            "INSERT INTO esm_schema_version (namespace, version, installed_rank, description, type, script, "
            "checksum, installed_by, installed_on, execution_time, success, query_results) VALUES (:namespace, "
            ":version, :rank, :description, 'NOSQL', :script, :checksum, 'ops', :installed_on, 2, :success, '[]')",
            {
                "namespace": namespace,
                "version": version,
                "rank": rank,
                "description": script.split("__", 1)[1],
                "script": script,
                "checksum": f"sha1-{version}".encode(),
                "installed_on": installed_on,
                "success": True,
            },
        )
        for namespace, version, rank, script in rows
    ]
    asyncio.run(execute(db_url, (v2_table_ddl(dialect), {}), *inserts))


def prepare_index(es, es_index, schema_dir):
    es.put(f"/{es_index}", json=json.loads(CREATE_INDEX.split("\n", 1)[1])).raise_for_status()
    es.put(f"/{es_index}/_doc/1", params={"refresh": "true"}, json={"user": "alice"}).raise_for_status()
    write_schemas(
        schema_dir,
        es_index,
        {V1_SCRIPTS[0]: CREATE_INDEX, V1_SCRIPTS[1]: INDEX_DOCUMENT, "V1_2__bulk_documents.esm": BULK_DOCUMENTS},
    )


@pytest.mark.parametrize("db_url", ["sqlite", "postgresql"], indirect=True)
def test_v1_installation_is_copied_by_init_and_continues(esmigrate, db_url, schema_dir, es, es_index, stored_rows):
    """Test fails if a v1 table is not refused, then copied by init and kept, and migrations do not resume"""
    create_v1_installation(db_url)
    prepare_index(es, es_index, schema_dir)

    result = esmigrate("upgrade")
    assert result.exit_code == Errors.ERR_DB_LEGACY_TABLE, result.output
    assert "Schema tables use the V1 layout, run `esmigrate init` to upgrade" in result.output
    assert doc_count(es, es_index) == 1

    result = esmigrate("init")
    assert result.exit_code == 0, result.output
    assert f"Copied V1 schema versions, previous table kept as {LEGACY_TABLE}" in result.output
    assert "latest version V1.1" in result.output

    rows = stored_rows()
    assert [(row.namespace, str(row.version), row.installed_rank, row.success) for row in rows] == [
        ("default", "1.0", 1, True),
        ("default", "1.1", 2, True),
    ]
    assert [row.script for row in rows] == V1_SCRIPTS
    assert [row.checksum for row in rows] == [b"sha1-1", b"sha1-2"]
    assert [row.execution_time for row in rows] == [1000, 1000]
    assert [row.installed_on for row in rows] == [value.astimezone(UTC) for value in V1_INSTALLED_ON]
    assert count_rows(db_url, "esm_schema_history") == 2
    (old,) = asyncio.run(execute(db_url, (f"SELECT version FROM {LEGACY_TABLE} ORDER BY version", {})))
    assert old == [("1.0",), ("1.1",)]

    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert "Processing schema create_index.esm" not in result.output
    assert "Schema database upgraded to 1.2" in result.output
    assert [str(row.version) for row in stored_rows()] == ["1.0", "1.1", "1.2"]
    assert doc_count(es, es_index) == 3

    result = esmigrate("init")
    assert result.exit_code == 0, result.output
    assert "Copied" not in result.output
    assert count_rows(db_url, "esm_schema_history") == 3


def test_v2_installation_is_copied_by_init_and_continues(esmigrate, db_url, schema_dir, es, es_index, stored_rows):
    """Test fails if a v2 table is not refused, then copied by init with its namespaces and UTC times unchanged"""
    create_v2_installation(
        db_url,
        [
            ("default", "1.0", 1, V1_SCRIPTS[0]),
            ("default", "1.1", 2, V1_SCRIPTS[1]),
            ("billing", "1.0", 1, V1_SCRIPTS[0]),
        ],
    )
    prepare_index(es, es_index, schema_dir)

    for command in ("upgrade", "rollback", "reset"):
        result = esmigrate(command)
        assert result.exit_code == Errors.ERR_DB_LEGACY_TABLE, result.output
        assert "Schema tables use the V2 layout, run `esmigrate init` to upgrade" in result.output

    result = esmigrate("init")
    assert result.exit_code == 0, result.output
    assert f"Copied V2 schema versions, previous table kept as {LEGACY_TABLE}" in result.output

    rows = stored_rows()
    assert [(str(row.version), row.installed_rank, row.success, row.execution_time) for row in rows] == [
        ("1.0", 1, True, 2000),
        ("1.1", 2, True, 2000),
    ]
    assert [row.script for row in rows] == V1_SCRIPTS
    assert [row.installed_on for row in rows] == [V2_INSTALLED_ON, V2_INSTALLED_ON]
    assert [str(row.version) for row in stored_rows("billing")] == ["1.0"]
    assert count_rows(db_url, "esm_schema_history") == 3
    assert count_rows(db_url, LEGACY_TABLE) == 3

    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert "Schema database upgraded to 1.2" in result.output
    assert [str(row.version) for row in stored_rows()] == ["1.0", "1.1", "1.2"]
    assert doc_count(es, es_index) == 3


def test_init_copies_nothing_when_old_versions_collide(esmigrate, db_url):
    """Test fails if init copies any row when two old versions are the same version"""
    create_v2_installation(db_url, [("default", "1.01", 1, V1_SCRIPTS[0]), ("default", "1.1", 2, V1_SCRIPTS[1])])
    result = esmigrate("init")
    assert result.exit_code == Errors.ERR_DB_IN_ERROR_STATE, result.output
    assert "default: 1.01 and 1.1 are the same version" in result.output
    assert count_rows(db_url, "esm_schema_state") == 0
    assert count_rows(db_url, "esm_schema_history") == 0
    assert count_rows(db_url, LEGACY_TABLE) == 2
