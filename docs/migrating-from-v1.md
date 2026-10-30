# Migrating from v1

ElasticMigrate 2.0 keeps the v1 model, versioned scripts recorded in a schema version table, and most of the
configuration. The following changes need attention when upgrading.

## Checklist

1. Install Python 3.11 or newer and ElasticMigrate 2.0 with the extra for your database (`[postgres]` or `[mysql]`).
2. Update `config.json` (see below): add `schema_dir` where it was missing, replace `?options=-csearch_path=…` with
   `schema_db_schema`, rename or select the profile, and decide on the script extension.
3. Run `esmigrate init` once per schema database to upgrade the v1 table.
4. Update scripts or pipelines that check exit codes or parse output.
5. Run `esmigrate upgrade` as before.

## Python and drivers

| | v1 | v2 |
|---|---|---|
| Python | 3.6–3.9 | 3.11+ |
| Database drivers | synchronous (any SQLAlchemy driver) | async: `aiosqlite` (built in), `asyncpg` (`[postgres]`), `asyncmy` (`[mysql]`) |

Plain URLs such as `postgresql://…` and `sqlite:///esmigrate.db` keep working and get the async driver
automatically. URLs naming a synchronous driver (`postgresql+psycopg2://…`) are rejected.

## Configuration

| Setting | v1 | v2 |
|---|---|---|
| Default profile | `test` | `default` (use `-p test` or rename the profile) |
| `schema_dir` | optional | required |
| `schema_ext` default | `.exm` | `.esm` (rename files, or set `"schema_ext": ".exm"`) |
| PostgreSQL schema | `?options=-csearch_path=…` in `schema_db` | `schema_db_schema` (the URL parameter is rejected) |
| Invalid `elastic_host` | silently replaced with `http://localhost:9200` | configuration error (exit code `11`) |
| Secrets | plain values | `${VAR}` references to environment variables |

A v1 PostgreSQL profile:

```text
"schema_db": "postgresql://migrator:secret@db.example.com/platform?options=-csearch_path%3Dsearch_migrations"
```

becomes:

```json
{
  "profiles": [
    {
      "default": {
        "schema_db": "postgresql://migrator:${ESMIGRATE_DB_PASSWORD}@db.example.com/platform",
        "schema_db_schema": "search_migrations",
        "schema_dir": "./migrations",
        "schema_ext": ".exm"
      }
    }
  ]
}
```

New optional fields cover TLS and authentication ([](security.md)), namespaces ([](databases.md)), the migration lock
([](locking.md)) and logging ([](logging.md)).

## Schema version table

v2 adds a namespace to the history, stores timestamps in UTC and keeps script paths relative to `schema_dir`. Every
command except `init` refuses to run against a v1 table (exit code `22`). `esmigrate init` upgrades it once, keeps the
original as `esm_schema_version_v1_backup` and moves the history into the `default` namespace. Drop the backup table
when you no longer need it.

v1 compared versions as decimal numbers, so `1.10` sorted before `1.9`. v2 compares version and sequence as whole
numbers. If your history uses sequence numbers of 10 or more, check that the applied versions match the order you
intended before upgrading.

## Exit codes and output

Exit codes are now positive and grouped by area. v1 used negative codes, which the shell saw as the values below:

| Failure | v1 (as seen by the shell) | v2 |
|---|---|---|
| Profile not found | `155` | `10` |
| Invalid configuration | n/a | `11` |
| Database connection failed | `55` | `20` |
| Database error or failed latest script | `54` | `21` |
| v1 table needs `init` | n/a | `22` |
| Migration lock held | n/a | `23` |
| Invalid schema directory | `211` | `30` |
| Invalid schema file | `210` | `31` |
| Invalid script | `209` | `32` |
| Invalid `--schema-version` | `111` | `40` |
| Elasticsearch error response | `11` | `50` |
| Elasticsearch unreachable | `10` | `51` |

Note that `10` meant "Elasticsearch unreachable" in v1 and means "profile not found" in v2.

Status messages are written to standard error; standard output only carries real output such as `esmigrate config`.

## Scripts

The script format is unchanged. Bodies are now always sent with a trailing newline, which fixes `_bulk` requests.
Elasticsearch 8 itself no longer supports mapping types, so scripts written for older clusters, such as
`PUT index/_mapping/doc`, must be rewritten in the typeless form (`PUT index/_mapping`).
