ElasticMigrate
==============
[![CI](https://github.com/zobayer1/elastic-migrate/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zobayer1/elastic-migrate/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/zobayer1/elastic-migrate/branch/main/graph/badge.svg)](https://codecov.io/gh/zobayer1/elastic-migrate)
[![Docs](https://github.com/zobayer1/elastic-migrate/actions/workflows/pages.yml/badge.svg?branch=main)](https://zobayer.net/elastic-migrate/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/zobayer1/elastic-migrate/blob/main/LICENSE)

### Schema migrations for Elasticsearch

ElasticMigrate (`esmigrate`) applies versioned schema scripts to Elasticsearch and records every run in SQL tables, in
the spirit of Flyway. Scripts run strictly in order, a failed script stops further migrations until it is resolved,
concurrent runs are locked out, and every run can leave an audit trail.

- Elasticsearch 8 over HTTP(S), with TLS, mutual TLS, basic authentication or API keys.
- Schema version history in SQLite, PostgreSQL or MySQL, in a dedicated schema and namespace if needed.
- Predictable exit codes for CI pipelines and scheduled jobs.

**Documentation:** [zobayer.net/elastic-migrate](https://zobayer.net/elastic-migrate/)
([quickstart](https://zobayer.net/elastic-migrate/quickstart.html),
[migrating from v1](https://zobayer.net/elastic-migrate/migrating-from-v1.html))

The `main` branch is working towards v3.0.0, and this README describes `main`. The documentation site describes the
latest release.

## Installation

ElasticMigrate requires Python 3.11 or newer. Signed releases are published on
[GitHub Releases](https://github.com/zobayer1/elastic-migrate/releases); see
[Downloads](https://zobayer.net/elastic-migrate/downloads.html) for verification steps.

```bash
python -m pip install "./elastic_migrate-2.0.0-py3-none-any.whl[postgres]"
```

Use the `postgres` or `mysql` extra for those databases; SQLite needs no extra.

## Quickstart

`config.json`:

```json
{
  "profiles": [
    {
      "default": {
        "elastic_host": "http://localhost:9200",
        "schema_db": "sqlite:///esmigrate.db",
        "schema_dir": "./migrations"
      }
    }
  ]
}
```

`migrations/V1_0__create_tweets_index.esm`:

```text
PUT /tweets
{"mappings": {"properties": {"user": {"type": "keyword"}, "message": {"type": "text"}}}}
```

Run it:

```bash
esmigrate init
esmigrate upgrade
```

## Configuration

`esmigrate` reads `config.json` from three places, in this order, and later files win field by field:

1. the user configuration directory, for example `~/.config/elastic-migrate/config.json` on Linux;
2. `config.json` in the current working directory;
3. the file named by the `ESMIGRATE_CONFIG` environment variable.

Each file holds a list of named profiles; select one with `-p`/`--profile` (default: `default`). Any string value may
reference an environment variable as `${NAME}`, which keeps secrets out of the file; an unset variable is an error.
`esmigrate config` prints the effective profile with passwords, API keys and `Authorization` headers masked.

| Field | Default | Description |
|---|---|---|
| `schema_dir` | (required) | Directory containing the migration scripts. |
| `schema_ext` | `.esm` | Script file extension. |
| `schema_db` | `sqlite:///esmigrate.db` | SQLAlchemy URL of the schema database (see [Supported databases](#supported-databases)). |
| `schema_db_schema` | none | PostgreSQL schema or MySQL database for the esmigrate tables; not allowed for SQLite. |
| `schema_namespace` | `default` | Separates the history of several projects stored in one database. |
| `lock_timeout` | `0` | Seconds to wait for the migration lock; `0` fails immediately. |
| `elastic_host` | `http://localhost:9200` | Elasticsearch URL (`http` or `https`), optionally with a path prefix. |
| `elastic_headers` | `{"Connection": "keep-alive"}` | Extra HTTP headers sent with every request. |
| `elastic_timeout` | `60` | Request timeout in seconds; `null` disables it. |
| `elastic_username` / `elastic_password` | none | Basic authentication. |
| `elastic_api_key` | none | Encoded API key, sent as `Authorization: ApiKey …`. |
| `elastic_ca_certs` | none | CA bundle used to verify the server certificate. |
| `elastic_verify_certs` | `true` | `false` skips certificate verification (test clusters only); a warning is printed on every run. |
| `elastic_client_cert` | none | Client certificate (chain) for mutual TLS. |
| `elastic_client_key` | none | Private key, if not included in `elastic_client_cert`. |
| `elastic_client_key_password` | none | Passphrase of an encrypted private key. |
| `log_file` | none | Debug log file with an audit trail; `--log-file` overrides it. |
| `log_rotation` | `size` | `size` rotates by size; `external` leaves rotation to logrotate. |
| `log_max_bytes` | `10485760` | Size limit for `size` rotation (10 MiB). |
| `log_backup_count` | `5` | Rotated files kept by `size` rotation. |

Invalid values fail when the profile is loaded, with exit code `11`. The `SCHEMA_PATTERN` environment variable overrides
the script file name pattern.

## Supported databases

| Database | `schema_db` URL | Driver | Extra |
|---|---|---|---|
| SQLite | `sqlite:///esmigrate.db` | `aiosqlite` | none |
| PostgreSQL | `postgresql://user:password@host:5432/database` | `asyncpg` | `postgres` |
| MySQL | `mysql://user:password@host:3306/database` | `asyncmy` | `mysql` |
| MariaDB | `mariadb://user:password@host:3306/database` | `asyncmy` | `mysql` |

The test suite runs against SQLite, PostgreSQL 17 and MySQL 8.4. Plain URLs get the async driver above; URLs naming an
async driver (`postgresql+asyncpg://…`) are used as given, and synchronous drivers are rejected.

esmigrate keeps applied versions in `esm_schema_state` and every run in the append-only `esm_schema_history`; SQLite
also gets `esm_schema_lock` for the migration lock. Databases written by v1 or v2 (`esm_schema_version`) must be
upgraded once with `esmigrate init`, which copies their rows into the new tables and leaves the old table untouched.

When the database account may not create tables, a DBA can create them from the generated SQL. Normal runs then only
need `SELECT`, `INSERT`, `UPDATE` and `DELETE` on those tables, plus `USAGE` on the `esm_schema_history` id sequence on
PostgreSQL:

```bash
esmigrate init --print-sql > esmigrate-tables.sql
```

## Development

You need Git, [uv](https://docs.astral.sh/uv/) and, for the integration tests, Docker with Compose v2. uv installs
Python 3.11 from `.python-version` when it is missing.

### Set up

```bash
git clone https://github.com/zobayer1/elastic-migrate.git
cd elastic-migrate
uv sync                      # creates .venv with Python 3.11 and the dev dependency group
uv run pre-commit install    # runs the hooks on every commit; repeat after recreating .venv
```

### Test stack

```bash
docker compose up -d --wait
```

| Service | Address | Credentials |
|---|---|---|
| Elasticsearch 8.19, plain HTTP | `http://localhost:9200` | none |
| Elasticsearch, HTTPS and basic authentication | `https://localhost:9201` | `elastic` / `esmigrate-secret` |
| Elasticsearch, HTTPS and client certificate (mutual TLS) | `https://localhost:9202` | `elastic` / `esmigrate-secret` and a client certificate |
| PostgreSQL 17 | `localhost:5432`, database `esmigrate` | `esmigrate` / `esmigrate` |
| MySQL 8.4 | `localhost:3306`, database `esmigrate` | `esmigrate` / `esmigrate`, root password `esmigrate` |

All ports are bound to `127.0.0.1`, the credentials are local test values, and no data survives `docker compose down`.
The one-shot `es-certs` service writes a test CA, server and client certificates to `.certs/` on the first start.

When a port is taken, move it with `ESMIGRATE_ES_PORT`, `ESMIGRATE_ES_SECURE_PORT`, `ESMIGRATE_ES_MTLS_PORT`,
`ESMIGRATE_PG_PORT` or `ESMIGRATE_MYSQL_PORT`, and point the tests at it, for example:

```bash
export ESMIGRATE_MYSQL_PORT=13306
export ESMIGRATE_TEST_MYSQL_URL=mysql://esmigrate:esmigrate@localhost:13306/esmigrate
export ESMIGRATE_TEST_MYSQL_ROOT_URL=mysql://root:esmigrate@localhost:13306/esmigrate
docker compose up -d --wait
```

The tests also read `ESMIGRATE_TEST_ES_URL`, `ESMIGRATE_TEST_PG_URL`, `ESMIGRATE_TEST_ES_SECURE_URL`,
`ESMIGRATE_TEST_ES_MTLS_URL`, `ESMIGRATE_TEST_ES_PASSWORD` and `ESMIGRATE_TEST_CERTS_DIR`.

### Tests

```bash
uv run pytest --cov                                   # unit tests; 100% branch coverage is required
uv run pytest tests/test_cli.py                       # one file (skip --cov: the coverage floor needs the full run)
uv run pytest tests/test_cli.py::test_cli_invocation_succeeds
uv run --isolated --python 3.14 pytest --cov          # the same suite on Python 3.14, without touching .venv
uv run pytest -m integration                          # integration tests against the test stack
```

Unit tests need no services. Integration tests run the real CLI against every database and Elasticsearch cluster of the
test stack; they are excluded from the default run and fail, rather than skip, when a service is down.

### Formatting, linting, type checking and hooks

```bash
uv run ruff format .                  # format (line length 120)
uv run ruff check --fix .             # lint, including import sorting
uv run pyright                        # type check: strict for esmigrate/, standard for tests/
uv run pre-commit run --all-files     # every hook on every file
```

The pre-commit hooks run ruff check, ruff format, the end-of-file and trailing whitespace fixers, shellcheck and pyright
over the whole project, including `tests/`.

### Documentation

```bash
uv run --group docs sphinx-build -W --keep-going -b html -d docs/_build/doctrees docs docs/_build/html
```

Pages are MyST Markdown in `docs/`. Every `config.json` example in a `json` code block there is loaded by the test
suite, so examples must stay valid.

### Build

```bash
uv build
```

This writes a wheel and a source archive to `dist/`. The version comes from Git tags, so a build between releases gets
a development version such as `2.0.1.dev8+g892a9cd96`. Release builds are reproducible and signed; see
[docs/development.md](docs/development.md).

### Try a build in a throwaway environment

Install the build into its own virtual environment and run it from a separate directory, so neither the project's
`.venv` nor its files are involved. With the test stack running:

```bash
uv build --out-dir /tmp/esm-try/dist
uv venv /tmp/esm-try/venv
uv pip install --python /tmp/esm-try/venv/bin/python "$(ls /tmp/esm-try/dist/*.whl)[postgres,mysql]"
mkdir -p /tmp/esm-try/migrations
cd /tmp/esm-try
```

Create `/tmp/esm-try/config.json`, which is read from the current directory:

```json
{
  "profiles": [
    {
      "default": {
        "elastic_host": "http://localhost:9200",
        "schema_db": "sqlite:///esm-try.db",
        "schema_dir": "./migrations"
      }
    }
  ]
}
```

Add `/tmp/esm-try/migrations/V1_0__create_tweets_index.esm` with the script from the [Quickstart](#quickstart), then:

```bash
source venv/bin/activate
esmigrate --version
esmigrate init --print-sql
esmigrate upgrade
esmigrate upgrade        # nothing to do
deactivate
```

### Cleanup

```bash
curl -X DELETE "localhost:9200/tweets"        # indices created while trying a build
docker compose down                           # stops the test stack and discards its data
rm -rf .certs                                 # optional: new test certificates on the next start
rm -rf /tmp/esm-try                           # the throwaway environment
rm -rf dist docs/_build htmlcov .coverage .pytest_cache
```

After removing `.venv`, run `uv sync` and `uv run pre-commit install` again.

## License

Licensed under the [Apache License 2.0](LICENSE). Releases up to `v1.0.0-alpha.1` were published under the MIT License.
