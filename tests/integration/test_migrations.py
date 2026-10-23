import json
from datetime import UTC

import pytest

from esmigrate.exceptions import Errors

CREATE_INDEX = """PUT /{index}
{"settings": {"number_of_shards": 1, "number_of_replicas": 0},
 "mappings": {"properties": {"user": {"type": "keyword"}, "message": {"type": "text"}}}}
"""
INDEX_DOCUMENT = """PUT /{index}/_doc/1?refresh=true
{"user": "alice", "message": "hello"}
"""
BULK_DOCUMENTS = """POST /{index}/_bulk?refresh=true
{"index": {"_id": "2"}}
{"user": "bob", "message": "hi"}
{"index": {"_id": "3"}}
{"user": "carol", "message": "hey"}
"""
ADD_FIELD = """PUT /{index}/_mapping
{"properties": {"created": {"type": "date"}}}
"""
DELETE_BY_QUERY = """POST /{index}/_delete_by_query?refresh=true
{"query": {"term": {"user": "bob"}}}
"""
BROKEN_DOCUMENT = """PUT /{index}/_doc/9?refresh=true
{"user": {"not": "a keyword"}}
"""

FULL_FLOW = {
    "V1_0__create_index.exm": CREATE_INDEX,
    "V1_1__index_document.exm": INDEX_DOCUMENT,
    "V1_2__bulk_documents.exm": BULK_DOCUMENTS,
    "V2_0__add_field.exm": ADD_FIELD,
    "V2_1__delete_by_query.exm": DELETE_BY_QUERY,
}


def write_schemas(schema_dir, index, scripts):
    for name, content in scripts.items():
        (schema_dir / name).write_text(content.replace("{index}", index), encoding="utf-8")


def versions(rows):
    return [(row.version, row.success) for row in rows]


def doc_count(es, index):
    return es.get(f"/{index}/_count").json()["count"]


def test_full_migration_flow(esmigrate, schema_dir, es, es_index, stored_rows, es_url):
    """Test fails if init and upgrade do not apply every script to elasticsearch and record them correctly"""
    write_schemas(schema_dir, es_index, FULL_FLOW)
    assert esmigrate("init").exit_code == 0
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert "Schema database upgraded to 2.1" in result.output

    properties = es.get(f"/{es_index}/_mapping").json()[es_index]["mappings"]["properties"]
    assert properties["user"]["type"] == "keyword"
    assert properties["created"]["type"] == "date"
    assert doc_count(es, es_index) == 2

    rows = stored_rows()
    assert versions(rows) == [("1.0", True), ("1.1", True), ("1.2", True), ("2.0", True), ("2.1", True)]
    assert [row.installed_rank for row in rows] == [1, 2, 3, 4, 5]
    assert [row.script for row in rows] == list(FULL_FLOW)
    for row in rows:
        assert row.query_results is not None
        assert es_url not in row.query_results
        assert row.installed_on is not None
        assert row.installed_on.tzinfo == UTC
    assert any(row.installed_on is not None and row.installed_on.microsecond for row in rows)
    bulk_result = json.loads(rows[2].query_results or "")
    assert bulk_result["query"].startswith(f"POST /{es_index}/_bulk")
    assert bulk_result["status"] == 200
    assert json.loads(bulk_result["result"])["errors"] is False


def test_failed_script_blocks_until_rollback(esmigrate, schema_dir, es, es_index, stored_rows):
    """Test fails if a failed script does not block upgrades until rolled back and fixed"""
    write_schemas(schema_dir, es_index, {"V1_0__create_index.exm": CREATE_INDEX, "V1_1__broken.exm": BROKEN_DOCUMENT})
    result = esmigrate("upgrade")
    assert result.exit_code == Errors.ERR_ES_HTTPERROR, result.output
    assert versions(stored_rows()) == [("1.0", True), ("1.1", False)]
    failed = stored_rows()[1].query_results or ""
    assert "document_parsing_exception" in failed or "mapper_parsing_exception" in failed

    assert esmigrate("upgrade").exit_code == Errors.ERR_DB_IN_ERROR_STATE
    assert esmigrate("rollback").exit_code == 0
    assert versions(stored_rows()) == [("1.0", True)]

    write_schemas(schema_dir, es_index, {"V1_1__broken.exm": INDEX_DOCUMENT})
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert versions(stored_rows()) == [("1.0", True), ("1.1", True)]
    assert doc_count(es, es_index) == 1


def test_partial_upgrade_then_rest(esmigrate, schema_dir, es, es_index, stored_rows):
    """Test fails if upgrade --schema-version does not stop at the target and resume from it later"""
    write_schemas(schema_dir, es_index, FULL_FLOW)
    result = esmigrate("upgrade", "--schema-version", "1.1")
    assert result.exit_code == 0, result.output
    assert versions(stored_rows()) == [("1.0", True), ("1.1", True)]
    assert doc_count(es, es_index) == 1

    assert esmigrate("upgrade").exit_code == 0
    assert [version for version, _ in versions(stored_rows())] == ["1.0", "1.1", "1.2", "2.0", "2.1"]
    assert doc_count(es, es_index) == 2


def test_reset_then_full_rerun(esmigrate, schema_dir, es, es_index, stored_rows):
    """Test fails if reset does not clear history so a full re-run against a fresh index succeeds"""
    write_schemas(schema_dir, es_index, FULL_FLOW)
    assert esmigrate("upgrade").exit_code == 0
    assert esmigrate("reset").exit_code == 0
    assert stored_rows() == []

    es.delete(f"/{es_index}").raise_for_status()
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert len(stored_rows()) == len(FULL_FLOW)
    assert doc_count(es, es_index) == 2


def test_namespaces_share_one_database(esmigrate, profile, tmp_path, es, es_index, stored_rows):
    """Test fails if two projects in different namespaces of one database see each other's history"""
    for namespace, scripts in (
        ("alpha", {"V1_0__create_index.exm": CREATE_INDEX, "V1_1__index_document.exm": INDEX_DOCUMENT}),
        ("beta", {"V1_0__create_index.exm": CREATE_INDEX}),
    ):
        schema_dir = tmp_path / namespace
        schema_dir.mkdir()
        write_schemas(schema_dir, f"{es_index}-{namespace}", scripts)
        profile(schema_dir=str(schema_dir), schema_namespace=namespace)
        result = esmigrate("upgrade")
        assert result.exit_code == 0, result.output

    assert versions(stored_rows("alpha")) == [("1.0", True), ("1.1", True)]
    assert versions(stored_rows("beta")) == [("1.0", True)]
    assert [row.installed_rank for row in stored_rows("beta")] == [1]
    assert doc_count(es, f"{es_index}-alpha") == 1
    assert doc_count(es, f"{es_index}-beta") == 0


@pytest.mark.parametrize("name", ["V2147483648_0__too_big.exm", "V1_99999999999__too_big.exm"])
def test_oversized_versions_are_rejected_before_running(esmigrate, schema_dir, es, es_index, stored_rows, name):
    """Test fails if a version that cannot be stored runs against elasticsearch before being rejected"""
    write_schemas(schema_dir, es_index, {"V1_0__create_index.exm": CREATE_INDEX, name: INDEX_DOCUMENT})
    result = esmigrate("upgrade")
    assert result.exit_code == Errors.ERR_INVALID_SCHEMA_FILE, result.output
    assert "Version number too large" in result.output
    assert es.head(f"/{es_index}").status_code == 404
    assert stored_rows() == []
