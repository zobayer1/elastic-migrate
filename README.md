ElasticMigrate
==============
[![CI](https://github.com/zobayer1/elastic-migrate/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zobayer1/elastic-migrate/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/zobayer1/elastic-migrate/branch/main/graph/badge.svg)](https://codecov.io/gh/zobayer1/elastic-migrate)
[![Docs](https://github.com/zobayer1/elastic-migrate/actions/workflows/pages.yml/badge.svg?branch=main)](https://zobayer.net/elastic-migrate/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/zobayer1/elastic-migrate/blob/main/LICENSE)

### Schema migrations for Elasticsearch

ElasticMigrate (`esmigrate`) applies versioned schema scripts to Elasticsearch and records every run in a SQL schema
version table, in the spirit of Flyway. Scripts run strictly in order, a failed script stops further migrations until it
is resolved, concurrent runs are locked out, and every run can leave an audit trail.

- Elasticsearch 8 over HTTP(S), with TLS, mutual TLS, basic authentication or API keys.
- Schema version history in SQLite, PostgreSQL or MySQL, in a dedicated schema and namespace if needed.
- Predictable exit codes for CI pipelines and scheduled jobs.

**Documentation:** [zobayer.net/elastic-migrate](https://zobayer.net/elastic-migrate/)
([quickstart](https://zobayer.net/elastic-migrate/quickstart.html),
[migrating from v1](https://zobayer.net/elastic-migrate/migrating-from-v1.html))

## Installation

ElasticMigrate requires Python 3.11 or newer. Signed releases are published on
[GitHub Releases](https://github.com/zobayer1/elastic-migrate/releases); see
[Downloads](https://zobayer.net/elastic-migrate/downloads.html) for verification steps.

    python -m pip install "./elastic_migrate-2.0.0-py3-none-any.whl[postgres]"

Use the `postgres` or `mysql` extra for those databases; SQLite needs no extra.

## Quickstart

`config.json`:

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

`migrations/V1_0__create_tweets_index.esm`:

    PUT /tweets
    {"mappings": {"properties": {"user": {"type": "keyword"}, "message": {"type": "text"}}}}

Run it:

    esmigrate init
    esmigrate upgrade

## License

Licensed under the [Apache License 2.0](LICENSE). Releases up to `v1.0.0-alpha.1` were published under the MIT License.
