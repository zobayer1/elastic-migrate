import sqlite3

from esmigrate.commons import Direction, Migration, MigVersion, ScriptData


def script(version, direction, content="PUT /twitter"):
    segment = f".{direction}" if direction else ""
    path = f"V{version.base}_{version.rank}__twitter{segment}.esm"
    return ScriptData(version, "twitter", "esm", path, content, direction)


def migration(text="1.0", up=True, down=True):
    version = MigVersion.parse(text)
    return Migration(
        up=script(version, Direction.UP) if up else None,
        down=script(version, Direction.DOWN, "DELETE /twitter") if down else None,
    )


async def record(db, text="1.0", success=True):
    run = await db.start_run(Direction.UP, migration(text))
    await db.finish_run(run, success, 5, f"results {text}")
    return run


def sqlite_path(db_url):
    return db_url.removeprefix("sqlite:///")


def query(db_url, sql):
    with sqlite3.connect(sqlite_path(db_url)) as conn:
        rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def execute(db_url, *statements):
    with sqlite3.connect(sqlite_path(db_url)) as conn:
        for statement in statements:
            conn.executescript(statement)
    conn.close()


def table_names(db_url):
    return {row[0] for row in query(db_url, "SELECT name FROM sqlite_master WHERE type = 'table'")}


def state_rows(db_url):
    return query(
        db_url,
        "SELECT namespace, version_base, version_rank, installed_rank, success, execution_time, query_results "
        "FROM esm_schema_state ORDER BY namespace, installed_rank",
    )


def history_rows(db_url):
    return query(
        db_url,
        "SELECT namespace, version_base, version_rank, operation, success, execution_time, query_results "
        "FROM esm_schema_history ORDER BY id",
    )
