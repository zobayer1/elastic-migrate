import asyncio
import sqlite3
from datetime import UTC, datetime

from sqlalchemy import insert, select

from esmigrate import cli
from esmigrate.commons import Direction, Migration, MigVersion, ScriptData
from esmigrate.internals import DBManager
from esmigrate.internals.migration_lock import LOCK_TABLE

ES_HOST = "http://es.example.com:9200"

LEGACY_TABLE_DDL = (
    "CREATE TABLE esm_schema_version (version VARCHAR NOT NULL PRIMARY KEY, version_base INTEGER, "
    "version_rank INTEGER, installed_rank INTEGER UNIQUE, description VARCHAR, type VARCHAR, script VARCHAR, "
    "checksum BLOB, installed_by VARCHAR, installed_on DATETIME, execution_time INTEGER, success BOOLEAN, "
    "query_results VARCHAR)"
)

V2_TABLE_DDL = (
    "CREATE TABLE esm_schema_version (namespace VARCHAR NOT NULL, version VARCHAR NOT NULL, version_base INTEGER, "
    "version_rank INTEGER, installed_rank INTEGER, description VARCHAR, type VARCHAR, script VARCHAR, "
    "checksum BLOB, installed_by VARCHAR, installed_on DATETIME, execution_time INTEGER, success BOOLEAN, "
    "query_results VARCHAR, PRIMARY KEY (namespace, version))"
)


def invoke(runner, *args):
    return runner.invoke(cli.main, ["--profile", "test", *args])


def write_schema(schema_dir, name, content="GET twitter"):
    (schema_dir / name).write_text(content)


def seed(context, *rows, namespace="default"):
    async def record_rows():
        async with DBManager.connect(context.schema_db, namespace=namespace) as db:
            for text, success in rows:
                version = MigVersion.parse(text)
                path = f"V{version.base}_{version.rank}__seeded.esm"
                run = await db.start_run(Direction.UP, Migration(up=ScriptData(version, "seeded", "esm", path, "")))
                if success is not None:
                    await db.finish_run(run, success, 1, "")

    asyncio.run(record_rows())


def stored_rows(context, namespace="default"):
    async def fetch_rows():
        async with DBManager.connect(context.schema_db, namespace=namespace) as db:
            return await db.find_all_schema()

    return asyncio.run(fetch_rows())


def versions(context, namespace="default"):
    return [str(row.version) for row in stored_rows(context, namespace)]


def history_rows(context, namespace="default"):
    async def fetch_rows():
        async with DBManager.connect(context.schema_db, namespace=namespace) as db:
            return await db.find_history()

    return asyncio.run(fetch_rows())


def raw_rows(context, sql):
    path = context.schema_db.removeprefix("sqlite:///")
    with sqlite3.connect(path) as conn:
        rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def create_legacy_table(context, rows=()):
    path = context.schema_db.removeprefix("sqlite:///")
    with sqlite3.connect(path) as conn:
        conn.execute(LEGACY_TABLE_DDL)
        for version, rank, success in rows:
            conn.execute(
                "INSERT INTO esm_schema_version (version, installed_rank, success, installed_on) VALUES (?, ?, ?, ?)",
                (version, rank, success, "2021-06-16 09:57:22"),
            )
    conn.close()


def create_v2_table(context, rows=()):
    path = context.schema_db.removeprefix("sqlite:///")
    with sqlite3.connect(path) as conn:
        conn.execute(V2_TABLE_DDL)
        for namespace, version, rank, success in rows:
            conn.execute(
                "INSERT INTO esm_schema_version (namespace, version, installed_rank, success, execution_time) "
                "VALUES (?, ?, ?, ?, 2)",
                (namespace, version, rank, success),
            )
    conn.close()


def hold_lock(context, host="other-host", pid=4242):
    async def insert_row():
        async with DBManager.connect(context.schema_db, namespace=context.schema_namespace) as db:
            async with db.lock():
                pass
            async with db._engine.begin() as conn:
                await conn.execute(
                    insert(LOCK_TABLE).values(
                        namespace=context.schema_namespace,
                        owner_host=host,
                        owner_pid=pid,
                        acquired_at=datetime.now(UTC),
                    )
                )

    asyncio.run(insert_row())


def lock_rows(context):
    async def fetch():
        async with DBManager.connect(context.schema_db) as db, db._engine.connect() as conn:
            return (await conn.execute(select(LOCK_TABLE))).mappings().all()

    return asyncio.run(fetch())
