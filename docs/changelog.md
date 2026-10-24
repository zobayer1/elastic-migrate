# Changelog

## 2.0.0 (unreleased)

A rewrite of ElasticMigrate for Python 3.11+ and Elasticsearch 8. See [](migrating-from-v1.md) for upgrade steps.

**Added**

- TLS with CA bundles, basic authentication, API keys and mutual TLS; `${VAR}` references in configuration values.
- PostgreSQL and MySQL as first-class schema databases, a configurable schema (`schema_db_schema`) and namespaces.
- Migration locks against concurrent runs, with `lock_timeout` and `esmigrate unlock`.
- Logging with `-v`/`-q`, a log file with size or external rotation, and an audit trail.
- Explicit upgrade of v1 schema version tables with `esmigrate init`.

**Changed**

- Async HTTP (`httpx`) and async SQLAlchemy 2; Python 3.11+.
- Default profile `default` (was `test`), default script extension `.esm` (was `.exm`), `schema_dir` required.
- Positive exit codes grouped by area; status messages on standard error.
- Versions compared as whole numbers; request paths and script paths stored without the Elasticsearch host.
- License changed from MIT to Apache-2.0.

**Fixed**

- `_bulk` requests failed without a trailing newline.
- Versions and sequences of 10 or more were ordered incorrectly.
- `elastic_host` values with single-label host names were silently replaced with localhost.
- `esmigrate COMMAND --help` required a loadable profile.

## 1.0.0-alpha.1 (2021-06-05)

First public pre-release.
