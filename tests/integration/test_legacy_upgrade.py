import asyncio
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import make_url, text

from esmigrate.exceptions import Errors
from esmigrate.internals.db_manager import LEGACY_BACKUP_TABLE, create_engine
from tests.integration.test_migrations import BULK_DOCUMENTS, CREATE_INDEX, INDEX_DOCUMENT, doc_count, write_schemas

V1_TYPES = {
    "sqlite": {"binary": "BLOB", "timestamp": "DATETIME"},
    "postgresql": {"binary": "BYTEA", "timestamp": "TIMESTAMP WITHOUT TIME ZONE"},
}
V1_INSTALLED_ON = [datetime(2021, 6, 16, 9, 57, 22, 123456), datetime(2021, 6, 17, 10, 0, 0)]
V1_SCRIPTS = ["V1_0__create_index.exm", "V1_1__index_document.exm"]


def v1_table_ddl(dialect):
    types = V1_TYPES[dialect]
    return (
        "CREATE TABLE esm_schema_version (version VARCHAR NOT NULL, version_base INTEGER, version_rank INTEGER, "
        f"installed_rank INTEGER, description VARCHAR, type VARCHAR, script VARCHAR, checksum {types['binary']}, "
        f"installed_by VARCHAR, installed_on {types['timestamp']}, execution_time INTEGER, success BOOLEAN, "
        "query_results VARCHAR, PRIMARY KEY (version), UNIQUE (installed_rank))"
    )


async def execute(db_url, *statements):
    engine = create_engine(db_url)
    try:
        async with engine.begin() as conn:
            results = [await conn.execute(text(sql), params) for sql, params in statements]
            return [result.all() if result.returns_rows else None for result in results]
    finally:
        await engine.dispose()


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


@pytest.mark.parametrize("db_url", ["sqlite", "postgresql"], indirect=True)
def test_v1_installation_is_upgraded_by_init_and_continues(esmigrate, db_url, schema_dir, es, es_index, stored_rows):
    """Test fails if a v1 table is not refused, then upgraded by init with a backup, and migrations do not resume"""
    create_v1_installation(db_url)
    es.put(f"/{es_index}", json=json.loads(CREATE_INDEX.split("\n", 1)[1])).raise_for_status()
    es.put(f"/{es_index}/_doc/1", params={"refresh": "true"}, json={"user": "alice"}).raise_for_status()
    write_schemas(
        schema_dir,
        es_index,
        {V1_SCRIPTS[0]: CREATE_INDEX, V1_SCRIPTS[1]: INDEX_DOCUMENT, "V1_2__bulk_documents.exm": BULK_DOCUMENTS},
    )

    result = esmigrate("upgrade")
    assert result.exit_code == Errors.ERR_DB_LEGACY_TABLE, result.output
    assert "esmigrate init" in result.output
    assert doc_count(es, es_index) == 1

    result = esmigrate("init")
    assert result.exit_code == 0, result.output
    assert f"previous table kept as {LEGACY_BACKUP_TABLE}" in result.output
    assert "latest version V1.1" in result.output

    rows = stored_rows()
    assert [(row.namespace, row.version, row.installed_rank, row.success) for row in rows] == [
        ("default", "1.0", 1, True),
        ("default", "1.1", 2, True),
    ]
    assert [row.script for row in rows] == V1_SCRIPTS
    assert [row.checksum for row in rows] == [b"sha1-1", b"sha1-2"]
    assert [row.installed_on for row in rows] == [value.astimezone(UTC) for value in V1_INSTALLED_ON]
    (backup,) = asyncio.run(execute(db_url, (f"SELECT version FROM {LEGACY_BACKUP_TABLE} ORDER BY version", {})))
    assert backup == [("1.0",), ("1.1",)]

    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert "Processing schema create_index.exm" not in result.output
    assert "Schema database upgraded to 1.2" in result.output
    assert [row.version for row in stored_rows()] == ["1.0", "1.1", "1.2"]
    assert doc_count(es, es_index) == 3

    result = esmigrate("init")
    assert result.exit_code == 0, result.output
    assert "Upgraded v1" not in result.output
