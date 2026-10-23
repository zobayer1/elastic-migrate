# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ElasticMigrate (`esmigrate` CLI, package name `elastic-migrate`) is a Flyway-style schema migration tool for Elasticsearch. It applies versioned schema script files against an ES cluster and records each run in a SQL "schema version" table (via SQLAlchemy). Last feature work was 2021 (tag `v1.0.0-alpha.1`); since then only bot dependency bumps. The repo is being **modernized** for newer Python and Elasticsearch versions — see "Current state" below before changing tooling or dependencies.

## Working rules

- **Minimal comments in source code.** The code is simple; tests do the explaining. Add a comment only when something is genuinely non-obvious. Explanations, design notes and user guides belong in `docs/`.
- **Maximum test coverage.** This module is used in enterprise, government-level applications. Every change ships with tests covering all new/changed branches, including error paths and exit codes; never lower coverage.
- **Plan before large changes.** For anything beyond a small fix, first write a plan and create/update the GitHub issue(s); implement only after that.
- Intermediate commits on `modernize` may leave tests broken; the branch must be green before the final PR.
- **Commits:** author `Zobayer Hasan <zobayer1@gmail.com>`; end every message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Commit messages only — no trailer or AI attribution in issue/PR bodies or comments. Show the proposed commit message to the user and wait for approval before committing. Reference issues with `Closes #N` / `Refs #N`.

## Commands

```bash
uv sync                                               # create/update .venv (Python 3.11 from .python-version) with dev group
uv run pre-commit install                             # (re)install git hook after .venv is recreated
uv run pytest --cov                                   # full suite, branch coverage, fails under the fail_under floor
uv run --isolated --python 3.14 pytest --cov          # same on 3.14 without touching .venv
uv run pytest tests/test_internals/test_script_parser.py   # single file
uv run pytest tests/test_cli.py::test_cli_upgrade_cmd_fails_with_value_error   # single test
uv run ruff check --fix .                             # lint (incl. import sorting, pyupgrade)
uv run ruff format .                                  # format
uv run pre-commit run --all-files                     # ruff check/format + whitespace/EOF fixers
docker compose up -d --wait                           # ES 8.19, PostgreSQL 17, MySQL 8.4 for integration tests
uv run pytest -m integration                          # integration tests (all three DBs + real ES), no coverage floor
docker compose down                                   # stop services (data is ephemeral)
uv build                                              # wheel + sdist
uv lock --upgrade                                     # manual dependency update (no bots)
```

- `uv run pytest` excludes integration tests (`addopts = -m "not integration"`). Integration tests fail, never skip, when a service is down. Ports can be moved with `ESMIGRATE_ES_PORT` / `ESMIGRATE_PG_PORT` / `ESMIGRATE_MYSQL_PORT`; tests read `ESMIGRATE_TEST_ES_URL` / `ESMIGRATE_TEST_PG_URL` / `ESMIGRATE_TEST_MYSQL_URL`. Compose credentials (`esmigrate`/`esmigrate`) are local test-only values.
- All config lives in `pyproject.toml`: build (hatchling + hatch-vcs), ruff, pytest (`DeprecationWarning`/`PendingDeprecationWarning` are errors), coverage (`fail_under` is a floor — raise it, never lower it). Only pass `--cov` for full runs, otherwise single-test runs trip the coverage floor.
- Version comes from git tags via hatch-vcs and is read at runtime with `importlib.metadata`, so the package must be installed (`uv sync` does this).

## Architecture

Flow of `esmigrate -p <profile> upgrade` (all orchestration lives in `esmigrate/cli.py`):

1. **`contexts.ContextConfig`** — `main()` loads the profile into `ctx.obj`; subcommands receive it via `@click.pass_obj`. Config files are read in order: user config dir (`platformdirs`), `./config.json`, then `$ESMIGRATE_CONFIG`; later files overwrite earlier ones. Profile fields: `elastic_host`, `elastic_headers`, `elastic_timeout` (default 60s, `null` disables), `schema_db`, `schema_dir`, `schema_ext`, `schema_namespace` (default `default`). Invalid values raise `InvalidConfigurationError`. Filename regex comes from `$SCHEMA_PATTERN` (named groups `version`, `sequence`, `name`, `extension`). Default profile is `test` (#108 renames it).
2. **`internals.GlobLoader.scan_dir`** (sync, local disk) — globs `schema_dir` for `*<schema_ext>`, validates names (`V1_10__name.exm` → version `"1.10"`, `version_key` `(1, 10)`), returns `commons.ScriptData` sorted by `version_key`, with `path` relative to `schema_dir`.
3. **`internals.ScriptParser.get_commands`** — Kibana-console-like script → `commons.Command`s: a `VERB path` line (GET/PUT/POST/DELETE) plus optional JSON/NDJSON body. Emits host-relative paths (`/twitter/_doc`); absolute and protocol-relative URLs are rejected.
4. **`internals.HTTPHandler`** — `async with HTTPHandler(ctx)` wraps one `httpx.AsyncClient` (base URL = `elastic_host`, profile headers, timeout). Non-2xx → `ElasticsearchHTTPError` (carries `.response`); transport errors/timeouts → `ElasticsearchConnError`. Plain HTTP by design — no elasticsearch-py client.
5. **`internals.DBManager`** — `async with DBManager.connect(url, namespace=..., upgrade=False)` creates the table and always disposes the async engine. Bare URLs are mapped to async drivers (`sqlite`→aiosqlite, `postgresql`/`postgres`→asyncpg, `mysql`/`mariadb`→aiomysql); sync drivers are rejected. Every query is scoped to the namespace.
6. **`models.SchemaVersion`** — table `esm_schema_version`, PK `(namespace, version)`, `installed_rank` unique per namespace, `installed_on` UTC via `models.types.UTCDateTime`. Portable across SQLite/PostgreSQL/MySQL; dialect differences use `with_variant`, never separate model classes.

Key behaviors:
- **Async boundary:** click commands are sync and call `sys.exit(asyncio.run(run_<command>(cfg)))`; async functions return exit codes instead of calling `sys.exit`, so `async with` cleanup always runs. Scripts and commands execute strictly sequentially.
- **Fail fast:** a failed script is still inserted with `success=False`; later `upgrade` runs refuse while the latest row is failed. `rollback` deletes failed rows, `reset` deletes all rows (both per namespace). An unreachable ES aborts without recording a row.
- **v1 tables:** a table without the `namespace` column raises `LegacySchemaTableError` (exit 22) for every command except `init`, which upgrades it explicitly and keeps `esm_schema_version_v1_backup`. No silent schema changes.
- Failure categories map to positive exit codes in the `exceptions.Errors` `IntEnum`, grouped by tens (1x profile/config, 2x DB, 3x schema files, 4x params, 5x HTTP); never use 1, 2, 126–127 or 128+ (uncaught error, click usage error, shell, signals). The shell sees exactly these values. The CLI prints `<ExceptionName>: <message>` via `cli.fail()`.
- Nothing stores the ES host: request paths in `query_results` are host-relative and `script` is relative to `schema_dir`.

## Coding style

- Python 3.11+ idioms, enforced by ruff (`E W F I UP B SIM C4 PT RUF ANN2`, line length 120): no encoding headers, no `(object)` bases, `X | None`, builtin generics, `typing.Self`, `collections.abc` types, `raise ... from err` inside `except`.
- Return type hints are required on all functions in `esmigrate/` (`ANN2`); tests are exempt.
- Private attributes use a leading underscore (`self._ctx`); short-lived locals and loop vars are often underscore-prefixed (`_path`, `_ver`, `_file`). f-strings throughout.
- Subpackages re-export their public API through `__init__.py` with an explicit `__all__`; import from the package (`from esmigrate.internals import ScriptParser`), not the submodule.
- Custom exceptions live in `esmigrate/exceptions/__init__.py`: subclass `RuntimeError`, one-line docstring `"""Raised when ..."""` plus `pass` (or a small `__init__` when they carry data, like `ElasticsearchHTTPError.response`), kept alphabetical and listed in `__all__`.
- Comments are sparse (see Working rules).

## Testing conventions

- Tests mirror the package layout: `tests/test_<subpackage>/test_<module>.py`, plus `tests/test_cli.py`.
- No live Elasticsearch needed for unit tests: `respx` (`respx_mock` fixture) fakes ES, real SQLite files in `tmp_path` back DB tests (in-memory SQLite does not work with async engines), `pyfakefs` (`fs`) for config/schema-file tests that need no DB, `pytest-mock` (`mocker`) only to inject failures, `monkeypatch` for env vars.
- Integration tests live in `tests/integration/` (auto-marked `integration`) and use the real CLI with a real `config.json` via `ESMIGRATE_CONFIG`. The `db_url` fixture parametrizes every test over SQLite, PostgreSQL and MySQL; `es_index` gives a unique index deleted afterwards. `asyncpg`/`aiomysql` are in the dev group so every dev env can reach all backends.
- Async tests are plain `async def` (`asyncio_mode = "auto"`). CLI tests must stay sync `def` because commands call `asyncio.run`; seed/inspect the DB there with `asyncio.run(...)`.
- Fixtures have a docstring (`"""pytest fixture for ..."""`). Parametrized tests often use an indirect `parameter` fixture (`@pytest.mark.parametrize("parameter", [...], indirect=["parameter"])`).
- Every test has a one-line docstring of the form `"""Test fails if ..."""`.
- CLI tests use `click.testing.CliRunner` and a `context` fixture that patches `ContextConfig.load_for` with a profile pointing at a temporary SQLite DB, a temporary `schema_dir` and a fake ES host; they run real commands end to end and assert `result.exit_code` against `Errors.*` plus the stored rows.
- Git: short imperative commit subjects. Modernization work happens on the `modernize` branch.

## Modernization decisions

- Plain HTTP to Elasticsearch via **async `httpx`** (no elasticsearch-py); **async SQLAlchemy** for the schema DB. SQLite is built in; PostgreSQL (`elastic-migrate[postgres]`, used by the enterprise deployments) and MySQL/MariaDB (`elastic-migrate[mysql]`) are first-class and must be tested.
- **Python ≥ 3.11 only**; test matrix is exactly 3.11 and 3.14. Code follows 3.11+ idioms: no `# -*- coding: utf-8 -*-` headers, no explicit `(object)` bases, `X | None` and builtin generics in hints.
- **uv** is the project manager (`uv sync`, `uv run`, `uv.lock`), with hatchling + hatch-vcs as build backend (#254).
- Target **Elasticsearch 8**; integration tests run against ES 8 plus PostgreSQL and MySQL in Docker (#259).
- Work is tracked through **GitHub issues** (milestone `v2.0.0`, label `modernization`, `gh issue list -m v2.0.0`). Reference the issue in commit messages (`Closes #N`). PRs are restricted to collaborators; a PR is opened only once the whole renovation is done.
- No automatic dependency updates (pyup removed, no Dependabot).

## Current state

- Done on `modernize`: #253 (CI/bot cleanup), #263 (Apache-2.0), #256 (SQLAlchemy 2), #254 (pyproject + uv), #255 (ruff, 3.11+ style), #257 (integer version ordering), #258 (async httpx + async DB, CLI rewrite), #59 (schema namespaces, UTC timestamps, explicit v1 table upgrade), #264 (positive exit codes).
- Remaining in milestone `v2.0.0`: #259 (Docker: ES 8 + PostgreSQL + MySQL integration tests), #260 (ES 8 TLS/auth, fixes #109 host validation), #261 (GitHub Actions on 3.11/3.14), #108 (default profile `default`), #64 (stdlib logging), #262 (docs incl. "Migrating from v1").
- Coverage is 100% with `fail_under = 100`.
