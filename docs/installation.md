# Installation

ElasticMigrate requires **Python 3.11 or newer** and is distributed as signed release artifacts on
[GitHub Releases](https://github.com/zobayer1/elastic-migrate/releases). It is not published to PyPI.

## Choose the database extra

The schema version history is stored in a SQL database. SQLite support is always included; PostgreSQL and MySQL need
an extra that installs the matching async driver.

| Database | Extra | Driver |
|---|---|---|
| SQLite | none | `aiosqlite` |
| PostgreSQL | `postgres` | `asyncpg` |
| MySQL / MariaDB | `mysql` | `asyncmy` |

## Install a release

Download the wheel of the release you want, verify it (see the release notes for the signing key and checksums), then
install it. Replace `2.0.0` with the release version.

```bash
python -m pip install "./elastic_migrate-2.0.0-py3-none-any.whl[postgres]"
```

With [uv](https://docs.astral.sh/uv/), install it as an isolated command-line tool:

```bash
uv tool install "elastic-migrate[postgres] @ ./elastic_migrate-2.0.0-py3-none-any.whl"
```

Use `[mysql]` for MySQL, or no extra for SQLite. Check the installation with:

```bash
esmigrate --version
```

## Install from source

```bash
git clone https://github.com/zobayer1/elastic-migrate.git
cd elastic-migrate
uv sync
uv run esmigrate --help
```
