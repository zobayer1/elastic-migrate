ElasticMigrate
==============
[![Python](https://img.shields.io/badge/python-3.6%20%7C%203.7%20%7C%203.8%20%7C%203.9-blueviolet?logo=python&logoColor=green)](https://www.python.org)
[![Build Status](https://travis-ci.org/zobayer1/elastic-migrate.svg?branch=main)](https://travis-ci.org/zobayer1/elastic-migrate)
[![codecov](https://codecov.io/gh/zobayer1/elastic-migrate/branch/main/graph/badge.svg)](https://codecov.io/gh/zobayer1/elastic-migrate)
[![Updates](https://pyup.io/repos/github/zobayer1/elastic-migrate/shield.svg)](https://pyup.io/repos/github/zobayer1/elastic-migrate)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/zobayer1/elastic-migrate/blob/main/LICENSE)

### Elasticsearch mapping migration tool
ElasticMigrate is a continuous schema migration tool for Elasticsearch. It is a very simple CLI tool that requires very little to no configuration and provides a convenient way to update your Elasticsearch mappings while keeping in line with your version control system. ElasticMigrate takes a "Fail Fast" approach for failed schema migrations by preventing further migrations until all errors are resolved. It also keeps track of all your previous migrations and provides schema file validation.

## Environment
ElasticMigrate has been tested on the following systems:

| Supported OS | Python Versions     |
|--------------|---------------------|
| Windows      | 3.6, 3.7, 3.8, 3.9  |
| MacOS        | 3.6, 3.7, 3.8, 3.9  |
| Linux        | 3.6, 3.7, 3.8, 3.9  |

## Configuration
ElasticMigrate can read configuration file `config.json` from three possible locations, in the following order:

1. From current working directory.
2. From user's app config directory. For example, in Linux: `~/.config/elastic-migrate/config.json`.
3. From environment variable `ESMIGRATE_CONFIG`.

If same profile fields are defined in multiple files, the latter overwrites the previous fields.

One or more configuration profiles:

    {
      "profiles": [
        {
          "my-profile": {
            "schema_db": "sqlite:///esmigrate.db",
            "elastic_host": "http://localhost:9200",
            "elastic_headers": {"Content-Type": "application/json"},
            "schema_ext": ".exm",
            "schema_dir": "./schema_dir"
          }
        }
      ]
    }

**schema_db:** Database connection string, must be compatible with SQLAlchemy connection URL formats.
**elastic_host:** Elasticsearch host URL.
**elastic_headers:** (Optional) Additional HTTP headers can be passed to be sent to Elasticsearch.
**schema_ext:** Schema file extension.
**schema_dir:** Schema directory path.

Example schema filenames:

    V1_1__create_index_mapping_for_twitter.exm
    V1_2__create_new_doc_in_twitter.exm
    V1_3__update_existing_doc_in_twitter.exm
    V1_4__delete_all_doc_in_twitter.exm
    V1_5__delete_index_twitter.exm

Default regex for parsing filenames:

    V(?P<version>[\\d]+)_(?P<sequence>[\\d]+)__(?P<name>[\\w]+)\\.(?P<extension>[\\w]+)

Regex pattern can be overridden by setting environment variable `SCHEMA_PATTERN`. The pattern must contain capture groups: `version`, `sequence`, `name`, `extension`. Do not include `r` notation with the regex pattern.

## Installation

### From the source:

    unzip elastic-migrate_{tags}.tar.gz
    cd elastic-migrate_{tags}
    pip install -e .

### From the wheel package:

    pip install elastic_migrate-{tags}.whl

It is recommended to use a virtualenv.

## Usage

After installation, run `esmigrate --help`, and `esmigrate {command} --help` for help menu.

## License

See [LICENSE](LICENSE)
