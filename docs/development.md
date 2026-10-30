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

## Releases

Releases are built by GitHub Actions and signed locally by the maintainer; the signing key never leaves the
maintainer's machine. Builds are reproducible: the build backend is pinned with hashes in `build-constraints.txt`,
`SOURCE_DATE_EPOCH` is set to the tagged commit's time, and `build-toolchain.env` pins the uv version and the
uv-managed CPython that build the archives. The interpreter matters because archive compression comes from its zlib:
a system Python linked against zlib-ng, as on Fedora, packs the same files into different bytes.

1. Update `docs/changelog.md` with the version and date, merge to `main` and wait for CI to pass.
2. Create a signed tag on `main` and push it:

   ```bash
   git tag -s v2.0.0 -m "ElasticMigrate 2.0.0"
   git push origin v2.0.0
   ```

3. The Release workflow runs the tests, builds the wheel and source archive, writes `SHA256SUMS`, attests build
   provenance and creates a draft release.
4. Verify, reproduce and sign the draft, first as a dry run:

   ```bash
   scripts/sign-release.sh --dry-run v2.0.0
   scripts/sign-release.sh v2.0.0
   ```

   The script checks that the release is a draft, that the tag is signed by a trusted release key, the checksums and
   attestations, and that a local rebuild from the tag is byte-identical. The rebuild runs the uv version pinned in the
   tag's `build-toolchain.env` through `uvx` and installs the pinned CPython into a temporary directory, so the local
   uv and Python installations are not involved. It then signs every file, uploads the signatures, publishes the
   release and starts the docs deployment from `main`, which refreshes the Downloads page. The site is always built
   from `main`, never from a tag.

To update the pinned build backend:

```bash
printf 'hatchling\nhatch-vcs\n' | uv pip compile - --universal --generate-hashes --python-version 3.11 --no-header -o build-constraints.txt
```

To update the pinned toolchain, set `UV_VERSION` to a uv release and `BUILD_PYTHON` to a CPython version that this uv
release can download:

```bash
uvx uv@0.13.6 python list --only-downloads --all-versions 3.11
```

## Continuous integration

GitHub Actions runs linting, type checking, unit and integration tests on Python 3.11 and 3.14, a package build check
and a documentation build on every push. Coverage is reported to Codecov.
