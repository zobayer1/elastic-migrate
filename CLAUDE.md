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
uv build                                              # wheel + sdist
uv lock --upgrade                                     # manual dependency update (no bots)
```

- All config lives in `pyproject.toml`: build (hatchling + hatch-vcs), ruff, pytest (`DeprecationWarning`/`PendingDeprecationWarning` are errors), coverage (`fail_under` is a floor — raise it, never lower it). Only pass `--cov` for full runs, otherwise single-test runs trip the coverage floor.
- Version comes from git tags via hatch-vcs and is read at runtime with `importlib.metadata`, so the package must be installed (`uv sync` does this).

## Architecture

Flow of `esmigrate -p <profile> upgrade` (all orchestration lives in `esmigrate/cli.py`):

1. **`contexts.ContextConfig`** — `main()` loads the profile into `ctx.obj`; every subcommand receives it via `@click.pass_obj`. Config files are read in order: user app config dir (`appdirs`), `./config.json`, then `$ESMIGRATE_CONFIG`; later files overwrite earlier ones (README claims cwd is read first — code disagrees). Filename regex comes from `$SCHEMA_PATTERN` and must contain named groups `version`, `sequence`, `name`, `extension`. Default profile is `test`.
2. **`internals.GlobLoader.scan_dir`** — globs `schema_dir` for `*<schema_ext>` files, validates names against the pattern (e.g. `V1_2__name.exm` → version `"1.2"`), wraps each in `commons.ScriptData` (with SHA1 checksum), sorted by (version, sequence).
3. **`internals.ScriptParser.get_commands`** — generator parsing a script into `commons.Command` objects. Kibana-console-like format: a line `VERB path` (GET/PUT/POST/DELETE, uppercase only; relative path, no scheme/host) followed by an optional body that must be valid JSON or NDJSON; Content-Type is chosen accordingly. Path is joined onto `es_host`.
4. **`internals.HTTPHandler.make_requests`** — sends each command with a raw `requests` session (not the elasticsearch-py client), merging profile `elastic_headers` (the only way to pass auth today); raises `HTTPError` on non-2xx and wraps connection failures in `ElasticsearchConnError`.
5. **`internals.DBManager`** (obtain via `get_db_manager(url)`, which caches one instance per URL in a module global) — persists `models.SchemaVersion` rows (table `esm_schema_version`, PK = version string, monotonically increasing `installed_rank`).

Key behaviors:
- **Fail fast**: a failed script is still inserted with `success=False`; later `upgrade` runs (and `insert_new_schema`) refuse to proceed while the latest row is failed. `rollback` deletes failed rows; `reset` deletes all rows.
- Each failure category maps to a negative exit code in `exceptions.Errors` (grouped by hundreds: -1xx profile, -2xx DB, -3xx schema files, -4xx params, -5xx HTTP). CLI commands catch domain exceptions, `click.echo(f"<ExceptionName>: {str(err)}")`, then `sys.exit(Errors.X)`.
- `GlobLoader`, `ScriptParser`, `HTTPHandler` take the `ContextConfig` via constructor or `init_ctx()`, and raise `ContextObjectNotSetError` if used without one.

## Coding style

- Python 3.11+ idioms, enforced by ruff (`E W F I UP B SIM C4 PT RUF ANN2`, line length 120): no encoding headers, no `(object)` bases, `X | None`, builtin generics, `typing.Self`, `collections.abc` types, `raise ... from err` inside `except`.
- Return type hints are required on all functions in `esmigrate/` (`ANN2`); tests are exempt.
- Private attributes use a leading underscore (`self._ctx`); short-lived locals and loop vars are often underscore-prefixed (`_path`, `_ver`, `_file`). f-strings throughout.
- Subpackages re-export their public API through `__init__.py` with an explicit `__all__`; import from the package (`from esmigrate.internals import ScriptParser`), not the submodule.
- Custom exceptions live in `esmigrate/exceptions/__init__.py`: subclass `RuntimeError` (or `ConnectionError`), one-line docstring `"""Raised when ..."""` plus `pass`, kept alphabetical and listed in `__all__`.
- Comments are sparse (see Working rules).

## Testing conventions

- Tests mirror the package layout: `tests/test_<subpackage>/test_<module>.py`, plus `tests/test_cli.py`.
- No live Elasticsearch or DB needed: `requests-mock` (`requests_mock` fixture) for HTTP, `pyfakefs` (`fs` fixture) for files/config, `pytest-mock` (`mocker`) for patching, `monkeypatch` for env vars.
- Fixtures are usually `scope="module"` with a docstring (`"""pytest fixture for ..."""`). Parametrized tests use an indirect `parameter` fixture (`@pytest.mark.parametrize("parameter", [...], indirect=["parameter"])`).
- Every test has a one-line docstring of the form `"""Test fails if ..."""`.
- CLI tests use `click.testing.CliRunner`, patch `esmigrate.cli.ContextConfig.load_for` to return a prebuilt context and `esmigrate.cli.get_db_manager` / `DBManager` methods, then assert `result.exit_code` against `Errors.*`.
- Git: short imperative commit subjects. Modernization work happens on the `modernize` branch.

## Modernization decisions

- Keep talking to Elasticsearch over plain HTTP requests (no elasticsearch-py), but move to **async with `httpx`**. The DB layer also goes **async** (SQLAlchemy async engine, `aiosqlite` by default).
- **Python ≥ 3.11 only**; test matrix is exactly 3.11 and 3.14. Code follows 3.11+ idioms: no `# -*- coding: utf-8 -*-` headers, no explicit `(object)` bases, `X | None` and builtin generics in hints.
- **uv** is the project manager (`uv sync`, `uv run`, `uv.lock`), with hatchling + hatch-vcs as build backend (#254).
- Target **Elasticsearch 8**; integration tests run against ES 8 in Docker.
- Work is tracked through **GitHub issues** (milestone `v2.0.0`, label `modernization`, issues #253–#262; `gh issue list -m v2.0.0`). Reference the issue in commit messages (`Closes #N`). PRs are restricted to collaborators; a PR is opened only once the whole renovation is done.
- No automatic dependency updates (pyup removed, no Dependabot).

## Current state (pre-modernization)

Verified on 2026-10-23 with Python 3.14 and latest unpinned deps (SQLAlchemy 2.1, click 8.5, pytest 9):
- SQLAlchemy 2.x deprecation failures fixed in #256 (2.0-style `DeclarativeBase`, `Mapped`, `select()`); tests pass on 3.11 and 3.14.
- Legacy tooling: Travis CI, Codecov and pyup removed in #253; setup.py/tox/requirements.txt replaced by `pyproject.toml` + uv in #254; black/flake8 replaced by ruff in #255.
- Elasticsearch-era assumptions: default host `http://localhost:9200` with no TLS/auth config (ES 8+ enables security by default); test fixtures use mapping types (`PUT twitter/_mapping/doc`), removed in ES 7/8.
- Known version-ordering bug: `ScriptData.version_base`/`version_rank` are regex-captured strings, so `GlobLoader` sorts lexicographically (`"10" < "9"`), and `cli.upgrade` compares versions as floats (`"1.10"` → `1.1` < `1.9`). Breaks once version or sequence reaches 10.
