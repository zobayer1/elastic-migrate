import asyncio

import pytest

from esmigrate.exceptions import Errors
from esmigrate.internals.db_manager import LEGACY_BACKUP_TABLE
from tests.integration.conftest import run_statements
from tests.integration.test_legacy_upgrade import V1_INSTALLED_ON, v1_table_ddl
from tests.integration.test_migrations import CREATE_INDEX, INDEX_DOCUMENT, doc_count, write_schemas

SERVER_BACKENDS = pytest.mark.parametrize("db_url", ["postgresql", "mysql"], indirect=True)


def default_schema(db_url):
    return "public" if db_url.startswith("postgresql") else "esmigrate"


@SERVER_BACKENDS
def test_tables_are_created_in_configured_schema(
    esmigrate, profile, db_url, db_schema, tables_in, schema_dir, es_index
):
    """Test fails if the schema version table is not created and used in schema_db_schema only"""
    write_schemas(schema_dir, es_index, {"V1_0__create.exm": CREATE_INDEX})
    profile(schema_db_schema=db_schema)
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert tables_in(db_schema) == ["esm_schema_version"]
    assert tables_in(default_schema(db_url)) == []


@SERVER_BACKENDS
def test_schemas_on_one_database_keep_separate_histories(esmigrate, profile, db_schemas, tmp_path, es, es_index):
    """Test fails if two projects in different schemas of one database share or block each other's history"""
    first, second = db_schemas(), db_schemas()
    for schema, scripts in (
        (first, {"V1_0__create.exm": CREATE_INDEX, "V1_1__document.exm": INDEX_DOCUMENT}),
        (second, {"V1_0__create.exm": CREATE_INDEX}),
    ):
        schema_dir = tmp_path / schema
        schema_dir.mkdir()
        write_schemas(schema_dir, f"{es_index}-{schema}", scripts)
        profile(schema_dir=str(schema_dir), schema_db_schema=schema)
        result = esmigrate("upgrade")
        assert result.exit_code == 0, result.output
        assert "Processing schema create.exm" in result.output
    assert doc_count(es, f"{es_index}-{first}") == 1
    assert doc_count(es, f"{es_index}-{second}") == 0
    profile(schema_db_schema=first)
    assert "latest version V1.1" in esmigrate("init").output
    profile(schema_db_schema=second)
    assert "latest version V1.0" in esmigrate("init").output


@SERVER_BACKENDS
def test_missing_schema_is_a_connection_error(esmigrate, profile):
    """Test fails if a schema that does not exist on the server is not reported with the connection exit code"""
    profile(schema_db_schema="esm_it_does_not_exist")
    result = esmigrate("init")
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED, result.output
    assert "Database schema esm_it_does_not_exist does not exist" in result.output


@pytest.mark.parametrize("db_url", ["postgresql"], indirect=True)
def test_v1_table_in_schema_is_upgraded(esmigrate, profile, db_url, db_schema, tables_in):
    """Test fails if a v1 table inside a PostgreSQL schema is not upgraded in place with its backup"""
    ddl = v1_table_ddl("postgresql").replace("TABLE esm_schema_version", f"TABLE {db_schema}.esm_schema_version")
    insert = (
        f"INSERT INTO {db_schema}.esm_schema_version (version, installed_rank, success, installed_on) "
        f"VALUES ('1.0', 1, true, '{V1_INSTALLED_ON[0].isoformat(' ')}')"
    )
    asyncio.run(run_statements(db_url, ddl, insert))
    profile(schema_db_schema=db_schema)
    assert esmigrate("upgrade").exit_code == Errors.ERR_DB_LEGACY_TABLE
    result = esmigrate("init")
    assert result.exit_code == 0, result.output
    assert "latest version V1.0" in result.output
    assert tables_in(db_schema) == ["esm_schema_version", LEGACY_BACKUP_TABLE]
    assert tables_in("public") == []
