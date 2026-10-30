# Schema databases

## Connection URLs

`schema_db` is a SQLAlchemy URL. Plain URLs get the matching async driver automatically:

| URL | Driver | Extra |
|---|---|---|
| `sqlite:///esmigrate.db` | `aiosqlite` | none |
| `postgresql://user:password@host:5432/database` | `asyncpg` | `postgres` |
| `mysql://user:password@host:3306/database` | `asyncmy` | `mysql` |

URLs naming an async driver explicitly (`postgresql+asyncpg://…`) are used as given; synchronous drivers such as
`psycopg2` are rejected. Unreachable or unsupported databases exit with code `20`.

## Dedicated schema

To keep the tables out of the default schema on a shared host, set `schema_db_schema`: a PostgreSQL schema, or a MySQL
database. The schema must exist; creating it is left to the database administrator.

```json
{
  "profiles": [
    {
      "default": {
        "schema_db": "postgresql://migrator:${ESMIGRATE_DB_PASSWORD}@db.example.com/platform",
        "schema_db_schema": "search_migrations",
        "schema_dir": "./migrations"
      }
    }
  ]
}
```

`schema_db_schema` replaces the psycopg2 style of selecting a schema in the URL, which is rejected:

```text
postgresql://migrator:secret@db.example.com/platform?options=-csearch_path%3Dsearch_migrations
```

## Namespaces

`schema_namespace` (default `default`) separates the history of several projects in one database and schema. Each
namespace has its own versions, ranks, failure state and migration lock.

## Tables

| Table | Purpose |
|---|---|
| `esm_schema_version` | One row per applied script, keyed by namespace and version. Timestamps are UTC. |
| `esm_schema_lock` | SQLite only: the migration lock. |
| `esm_schema_version_v1_backup` | Created once by `esmigrate init` when it upgrades a v1 table; safe to drop afterwards. |

## Upgrading from ElasticMigrate v1

Tables created by v1 are detected automatically. Every command except `init` refuses to run (exit code `22`) until you
run `esmigrate init` once. `init` copies the old table to `esm_schema_version_v1_backup`, recreates
`esm_schema_version`, and copies the history into the `default` namespace, with script paths reduced to file names and
timestamps converted from local time to UTC. On PostgreSQL the upgrade runs in one transaction; on every database the
backup table keeps the original history.
