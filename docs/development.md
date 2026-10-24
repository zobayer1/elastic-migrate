# Development

ElasticMigrate uses [uv](https://docs.astral.sh/uv/) and supports Python 3.11 and newer.

```bash
git clone https://github.com/zobayer1/elastic-migrate.git
cd elastic-migrate
uv sync
uv run pre-commit install
```

## Checks

| Command | Purpose |
|---|---|
| `uv run pytest --cov` | Unit tests with branch coverage; 100% is required. |
| `uv run ruff check --fix .` and `uv run ruff format .` | Lint and format (line length 120). |
| `uv run pyright` | Type checking: strict for `esmigrate/`, standard for `tests/`. |
| `uv run pre-commit run --all-files` | All of the above hooks. |

## Integration tests

Integration tests run the real CLI against Elasticsearch 8 (plain, HTTPS and mutual TLS), PostgreSQL 17 and MySQL 8.4
in Docker. They are excluded from the default test run and fail, rather than skip, when a service is down.

```bash
docker compose up -d --wait
uv run pytest -m integration
docker compose down
```

The compose stack generates a throwaway CA and certificates into `.certs/` on first start.

## Documentation

```bash
uv run --group docs sphinx-build -W --keep-going -b html -d docs/_build/doctrees docs docs/_build/html
```

Pages are MyST Markdown in `docs/`. Every `config.json` example in a `json` code block is loaded by the test suite, so
examples must stay valid. The site is deployed to GitHub Pages from `main`.

## Continuous integration

GitHub Actions runs linting, type checking, unit and integration tests on Python 3.11 and 3.14, a package build check
and a documentation build on every push. Coverage is reported to Codecov.
