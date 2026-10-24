# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ElasticMigrate (`esmigrate` CLI, package name `elastic-migrate`) is a Flyway-style schema migration tool for Elasticsearch. It applies versioned schema script files against an ES cluster and records each run in a SQL "schema version" table (via SQLAlchemy). Last feature work was 2021 (tag `v1.0.0-alpha.1`); since then only bot dependency bumps. The repo is being **modernized** for newer Python and Elasticsearch versions — see "Current state" below before changing tooling or dependencies.

## Working rules

- **Minimal comments in source code.** The code is simple; tests do the explaining. Add a comment only when something is genuinely non-obvious. Explanations, design notes and user guides belong in `docs/`.
- **Maximum test coverage.** This module is used in enterprise, government-level applications. Every change ships with tests covering all new/changed branches, including error paths and exit codes; never lower coverage.
- **Plan before large changes.** For anything beyond a small fix, first write a plan and create/update the GitHub issue(s); implement only after that.
- Intermediate commits on `modernize` may leave tests broken; the branch must be green before the final PR.
- **Commits:** author `Zobayer Hasan <zobayer1@gmail.com>`; end every message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and nothing else (no `Claude-Session` links). Commit messages only — no trailer or AI attribution in issue/PR bodies or comments. Show the proposed commit message to the user and wait for approval before committing. Reference issues with `Closes #N` / `Refs #N`.

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
uv run pyright                                        # type check: strict for esmigrate/, standard for tests/
uv run pre-commit run --all-files                     # ruff check/format, whitespace/EOF fixers, pyright
docker compose up -d --wait                           # ES 8.19 (plain :9200, HTTPS+auth :9201, mTLS :9202), PostgreSQL 17, MySQL 8.4
uv run pytest -m integration                          # integration tests (all three DBs + real ES), no coverage floor
docker compose down                                   # stop services (data is ephemeral)
uv build                                              # wheel + sdist
uv lock --upgrade                                     # manual dependency update (no bots)
```

- `uv run pytest` excludes integration tests (`addopts = -m "not integration"`). Integration tests fail, never skip, when a service is down. Ports can be moved with `ESMIGRATE_ES_PORT` / `ESMIGRATE_PG_PORT` / `ESMIGRATE_MYSQL_PORT`; tests read `ESMIGRATE_TEST_ES_URL` / `ESMIGRATE_TEST_PG_URL` / `ESMIGRATE_TEST_MYSQL_URL` (plus `ESMIGRATE_TEST_MYSQL_ROOT_URL`, used only to create per-test MySQL databases for `schema_db_schema` tests; PostgreSQL schemas are created by the `esmigrate` owner). Compose credentials (`esmigrate`/`esmigrate`, ES `elastic`/`esmigrate-secret`) are local test-only values. The one-shot `es-certs` service writes a test CA, server and client certificate to the git-ignored `.certs/` (reused across runs; delete it to regenerate). Secured clusters move with `ESMIGRATE_ES_SECURE_PORT` / `ESMIGRATE_ES_MTLS_PORT`; tests read `ESMIGRATE_TEST_ES_SECURE_URL` / `ESMIGRATE_TEST_ES_MTLS_URL` / `ESMIGRATE_TEST_ES_PASSWORD` / `ESMIGRATE_TEST_CERTS_DIR`.
- All config lives in `pyproject.toml`: build (hatchling + hatch-vcs), ruff, pytest (`DeprecationWarning`/`PendingDeprecationWarning` are errors), coverage (`fail_under` is a floor — raise it, never lower it). Only pass `--cov` for full runs, otherwise single-test runs trip the coverage floor.
- Version comes from git tags via hatch-vcs and is read at runtime with `importlib.metadata`, so the package must be installed (`uv sync` does this).

## CI

- `.github/workflows/ci.yml` runs on every push, PRs to `main` and manually: `lint` (pre-commit incl. strict pyright), `unit` and `integration` (Python 3.11 and 3.14; integration starts the full `docker compose` stack), `build` (`uv build` + `twine check --strict`). Jobs call the same `uv run …` commands used locally.
- Coverage goes to Codecov via **OIDC** (`use_oidc: true`, `id-token: write`) — no token secret; flags `unit` / `integration`.
- Action versions: use the newest major releases and check `runs.using` is `node24` (no deprecated Node runtimes). Actions that receive a write token, a secret or an OIDC token are pinned to a commit SHA with a `# vX.Y.Z` comment; others use major tags where the publisher maintains them (`astral-sh/setup-uv` publishes no major tags, so it is SHA-pinned too — check `gh api repos/<owner>/<repo>/git/ref/tags/vN` before using a major tag). Validate workflow edits with `uvx --from actionlint-py actionlint`.

## Architecture

Flow of `esmigrate -p <profile> upgrade` (all orchestration lives in `esmigrate/cli.py`):

1. **`contexts.ContextConfig`** — `main()` loads the profile into `ctx.obj`; subcommands receive it via `@click.pass_obj`. Config files are read in order: user config dir (`platformdirs`), `./config.json`, then `$ESMIGRATE_CONFIG`; later files overwrite earlier ones. Profile fields: `elastic_host` (http/https URL, any host incl. single-label names, no embedded credentials), `elastic_headers`, `elastic_timeout` (default 60s, `null` disables), `elastic_username`/`elastic_password` or `elastic_api_key`, `elastic_ca_certs`, `elastic_verify_certs` (default true; false prints a warning every run), `elastic_client_cert`/`elastic_client_key`/`elastic_client_key_password` (mTLS), `schema_db`, `lock_timeout` (seconds, default 0), `schema_db_schema` (PostgreSQL schema / MySQL database for the esm tables; rejected for SQLite; psycopg2 `?options=` URL parameters are rejected in favour of it), `schema_dir` (**required**, no fallback to the working directory), `schema_ext` (default `.esm`; v1 default was `.exm`), `schema_namespace` (default `default`). Missing or invalid values raise `InvalidConfigurationError` (exit 11) at profile load. Filename regex comes from `$SCHEMA_PATTERN` (named groups `version`, `sequence`, `name`, `extension`). Profiles from all config files are merged per field, then every string value (also nested in headers/lists) has `${VAR}` references resolved from the environment — an unset variable is an error. `esmigrate config` masks passwords, API keys and `Authorization` headers. Default profile is `default` (`commons.DEFAULT_PROFILE`; was `test` in v1, #108).
2. **`internals.GlobLoader.scan_dir`** (sync, local disk) — globs `schema_dir` for `*<schema_ext>`, validates names (`V1_10__name.esm` → version `"1.10"`, `version_key` `(1, 10)`), returns `commons.ScriptData` sorted by `version_key`, with `path` relative to `schema_dir`.
3. **`internals.ScriptParser.get_commands`** — Kibana-console-like script → `commons.Command`s: a `VERB path` line (GET/PUT/POST/DELETE) plus optional JSON/NDJSON body. Emits host-relative paths (`/twitter/_doc`); absolute and protocol-relative URLs are rejected.
4. **`internals.HTTPHandler`** — `async with HTTPHandler(ctx)` wraps one `httpx.AsyncClient` (base URL = `elastic_host`, profile headers, timeout). Non-2xx → `ElasticsearchHTTPError` (carries `.response`); transport errors/timeouts → `ElasticsearchConnError`. Plain HTTP by design — no elasticsearch-py client.
5. **`internals.DBManager`** — `async with DBManager.connect(url, namespace=..., upgrade=False)` creates the table and always disposes the async engine. Bare URLs are mapped to async drivers (`sqlite`→aiosqlite, `postgresql`/`postgres`→asyncpg, `mysql`/`mariadb`→asyncmy); sync drivers are rejected. Every query is scoped to the namespace. `schema=` applies `schema_translate_map` to the engine, and raw SQL / inspection pass the schema explicitly (`qualified_name`); a missing schema is an `InvalidDBConnectionError`.
6. **`models.SchemaVersion`** — table `esm_schema_version`, PK `(namespace, version)`, `installed_rank` unique per namespace, `installed_on` UTC via `models.types.UTCDateTime`. Portable across SQLite/PostgreSQL/MySQL; dialect differences use `with_variant`, never separate model classes.

Key behaviors:
- **Async boundary:** click commands are sync and call `sys.exit(asyncio.run(run_<command>(cfg)))`; async functions return exit codes instead of calling `sys.exit`, so `async with` cleanup always runs. Scripts and commands execute strictly sequentially.
- **Fail fast:** a failed script is still inserted with `success=False`; later `upgrade` runs refuse while the latest row is failed. `rollback` deletes failed rows, `reset` deletes all rows (both per namespace). An unreachable ES aborts without recording a row.
- **Migration lock:** `upgrade`, `rollback` and `reset` hold a lock per (schema database, schema, namespace) for the whole run via `DBManager.lock()` (`internals.migration_lock`): PostgreSQL advisory locks and MySQL `GET_LOCK` on a dedicated autocommit connection (released automatically if the process dies), a lock row in `esm_schema_lock` on SQLite (stale holders on the same host with a dead pid are taken over; never on Windows, where `os.kill(pid, 0)` would send CTRL_C). `lock_timeout` (default 0) controls waiting; a held lock is `MigrationLockedError` (exit 23) naming the holder. `esmigrate unlock` removes a stuck SQLite lock after confirmation. `init` is not locked.
- **v1 tables:** a table without the `namespace` column raises `LegacySchemaTableError` (exit 22) for every command except `init`, which upgrades it explicitly and keeps `esm_schema_version_v1_backup`. No silent schema changes.
- Failure categories map to positive exit codes in the `exceptions.Errors` `IntEnum`, grouped by tens (1x profile/config, 2x DB, 3x schema files, 4x params, 5x HTTP); never use 1, 2, 126–127 or 128+ (uncaught error, click usage error, shell, signals). The shell sees exactly these values. The CLI prints `<ExceptionName>: <message>` via `cli.fail()`.
- **Logging:** everything logs under `esmigrate` (`logging.getLogger(__name__)`); only the CLI configures handlers (`commons.log_setup`). Console handler on **stderr** (INFO default, `-v` DEBUG, `-q` warnings/errors); **stdout** is reserved for real output (`config`, `--version`, banner). Optional log file (`log_file` profile field or `--log-file`, always DEBUG, UTC timestamps) with `log_rotation: size` (`RotatingFileHandler`, `log_max_bytes` 10 MiB, `log_backup_count` 5) or `external` (`WatchedFileHandler` for logrotate). The audit trail records run start (version, command, profile, namespace, host, masked DB URL, OS user, machine), each script (file, checksum, result, duration), each request (verb, path, sizes, status, duration) and the exit code. Never log credentials, `Authorization` headers or request/response bodies; DB URLs go through `mask_db_url`. `tests/conftest.py` closes esmigrate log handlers after every test.
- Nothing stores the ES host: request paths in `query_results` are host-relative and `script` is relative to `schema_dir`.

## Coding style

- Python 3.11+ idioms, enforced by ruff (`E W F I UP B SIM C4 PT RUF ANN2 TID252`, line length 120): no encoding headers, no `(object)` bases, `X | None`, builtin generics, `typing.Self`, `collections.abc` types, `raise ... from err` inside `except`.
- Return type hints are required on all functions in `esmigrate/` (`ANN2`); tests are exempt.
- pyright must report 0 errors: **strict** mode for `esmigrate/` (no unknown types — annotate empty collections, use `dict[str, str]`/`tuple[...]` not bare generics, `cast` JSON values after `isinstance`), standard mode for `tests/`. Narrow optionals with `assert x is not None` / `isinstance` in tests; use `SCHEMA_TABLE` (typed `Table`) instead of `SchemaVersion.__table__`. Use `-> AsyncGenerator[T, None]` (not `AsyncIterator`) for `@asynccontextmanager`.
- Private attributes use a leading underscore (`self._ctx`); short-lived locals and loop vars are often underscore-prefixed (`_path`, `_ver`, `_file`). f-strings throughout.
- Imports are always absolute and fully qualified (`from esmigrate.commons.command import Command`), never relative (`from .command import ...`); ruff `TID252` enforces this.
- Subpackages re-export their public API through `__init__.py` with an explicit `__all__`; import from the package (`from esmigrate.internals import ScriptParser`), not the submodule.
- Custom exceptions live in `esmigrate/exceptions/__init__.py`: subclass `RuntimeError`, one-line docstring `"""Raised when ..."""` plus `pass` (or a small `__init__` when they carry data, like `ElasticsearchHTTPError.response`), kept alphabetical and listed in `__all__`.
- Comments are sparse (see Working rules).

## Testing conventions

- Tests mirror the package layout: `tests/test_<subpackage>/test_<module>.py`, plus `tests/test_cli.py`.
- No live Elasticsearch needed for unit tests: `respx` (`respx_mock` fixture) fakes ES, real SQLite files in `tmp_path` back DB tests (in-memory SQLite does not work with async engines), `pyfakefs` (`fs`) for config/schema-file tests that need no DB, `pytest-mock` (`mocker`) only to inject failures, `monkeypatch` for env vars.
- Integration tests live in `tests/integration/` (auto-marked `integration`) and use the real CLI with a real `config.json` via `ESMIGRATE_CONFIG`. The `db_url` fixture parametrizes every test over SQLite, PostgreSQL and MySQL; `es_index` gives a unique index deleted afterwards. `asyncpg`/`asyncmy` are in the dev group so every dev env can reach all backends.
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

- Done on `modernize`: #253 (CI/bot cleanup), #263 (Apache-2.0), #256 (SQLAlchemy 2), #254 (pyproject + uv), #255 (ruff, 3.11+ style), #257 (integer version ordering), #258 (async httpx + async DB, CLI rewrite), #59 (schema namespaces, UTC timestamps, explicit v1 table upgrade), #264 (positive exit codes), #265 (pyright), #259 (Docker integration tests on all three DBs), #260 + #109 (TLS, mTLS, basic/API-key auth, `${VAR}` interpolation, strict host validation), #261 (CI, Codecov OIDC, auto-assign), #108 (default profile `default`), #64 (logging, log file, audit trail), #268 (configurable database schema), #267 (migration lock), #266 (default extension `.esm`; v1 used `.exm`).
- Remaining in milestone `v2.0.0`: #262 (docs incl. "Migrating from v1") — deliberately done **after** the modernization PR is merged into `main`.
- Coverage is 100% with `fail_under = 100`.
