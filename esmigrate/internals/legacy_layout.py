import re
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Connection, insert, inspect, literal, select, table, text

from esmigrate.commons import DEFAULT_NAMESPACE, MigVersion, Operation
from esmigrate.exceptions import SchemaVersionSqlDbError, error_list
from esmigrate.models import HISTORY_TABLE, STATE_TABLE

LEGACY_TABLE = "esm_schema_version"


class Layout(StrEnum):
    """Table layout found in the schema database"""

    CURRENT = "CURRENT"
    V1 = "V1"
    V2 = "V2"


def old_timestamp_to_utc(value: datetime | str | None, force_utc: bool = False) -> datetime | None:
    """Convert a v1 local or v2 UTC timestamp into an aware UTC datetime"""
    if value is None:
        return None
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    if stamp.tzinfo is None and force_utc:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def qualified_name(conn: Connection, table: str, schema: str | None) -> str:
    """Quote a table name, prefixed with its schema when one is set"""
    preparer = conn.dialect.identifier_preparer
    name = preparer.quote(table)
    return f"{preparer.quote_schema(schema)}.{name}" if schema else name


def table_has_rows(conn: Connection, table_name: str, schema: str | None = None) -> bool:
    """Tell whether a table exists and has at least one row"""
    if not inspect(conn).has_table(table_name, schema=schema):
        return False
    stmt = select(literal(1)).select_from(table(table_name, schema=schema)).limit(1)
    return conn.scalar(stmt) is not None


def detect_layout(conn: Connection, schema: str | None = None) -> Layout:
    """Detect whether the database still holds v1 or v2 rows to copy"""
    if table_has_rows(conn, HISTORY_TABLE.name, schema=schema) or not table_has_rows(conn, LEGACY_TABLE, schema):
        return Layout.CURRENT
    columns = {col["name"] for col in inspect(conn).get_columns(LEGACY_TABLE, schema=schema)}
    return Layout.V2 if "namespace" in columns else Layout.V1


def old_row_to_state(row: Mapping[Any, Any], namespace: str, version: MigVersion, layout: Layout) -> dict[str, Any]:
    """Convert a v1 or v2 row into a state row"""
    script = row["script"]
    if script and layout is Layout.V1:
        script = re.split(r"[\\/]", script)[-1]
    elapsed = row["execution_time"]
    success = row["success"]
    return {
        "namespace": namespace,
        "version_base": version.base,
        "version_rank": version.rank,
        "installed_rank": row["installed_rank"],
        "description": row["description"],
        "type": row["type"],
        "script": script,
        "checksum": row["checksum"],
        "installed_by": row["installed_by"],
        "installed_on": old_timestamp_to_utc(row["installed_on"], layout is Layout.V2),
        "execution_time": None if elapsed is None else elapsed * 1000,
        "success": None if success is None else bool(success),
        "query_results": row["query_results"],
    }


def state_to_history(state: Mapping[str, Any]) -> dict[str, Any]:
    """Build the history row recorded for a copied state row"""
    return {
        "namespace": state["namespace"],
        "version_base": state["version_base"],
        "version_rank": state["version_rank"],
        "operation": Operation.UP.value,
        "description": state["description"],
        "script": state["script"],
        "checksum": state["checksum"],
        "executed_by": state["installed_by"],
        "executed_on": state["installed_on"],
        "execution_time": state["execution_time"],
        "success": state["success"],
        "query_results": state["query_results"],
    }


def copy_old_rows(conn: Connection, layout: Layout, schema: str | None = None) -> None:
    """Copy every v1 or v2 row into the new tables, refusing unusable or colliding versions"""
    source = qualified_name(conn, LEGACY_TABLE, schema)
    rows = conn.execute(text(f"SELECT * FROM {source}")).mappings().all()

    seen: dict[tuple[str, MigVersion], str] = {}
    states: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in sorted(rows, key=lambda item: item["version"]):
        namespace = row["namespace"] if layout is Layout.V2 else DEFAULT_NAMESPACE
        try:
            version = MigVersion.parse(row["version"])
        except ValueError as err:
            errors.append(f"{namespace}: {err}")
            continue
        earlier = seen.setdefault((namespace, version), row["version"])
        if earlier != row["version"]:
            errors.append(f"{namespace}: {earlier} and {row['version']} are the same version")
            continue
        states.append(old_row_to_state(row, namespace, version, layout))
    if errors:
        raise SchemaVersionSqlDbError(error_list("Cannot copy existing schema versions:", errors))

    states.sort(key=lambda state: (state["namespace"], state["installed_rank"] or 0))
    conn.execute(insert(STATE_TABLE), states)
    conn.execute(insert(HISTORY_TABLE), [state_to_history(state) for state in states])
