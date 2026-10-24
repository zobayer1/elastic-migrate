# Configuration

## Configuration files

ElasticMigrate reads `config.json` files from three places, in this order:

1. the user configuration directory, for example `~/.config/elastic-migrate/config.json` on Linux;
2. `config.json` in the current working directory;
3. the file named by the `ESMIGRATE_CONFIG` environment variable.

Each file holds a list of named profiles. When the same profile appears in several files, its fields are merged and
later files win field by field. Files that are missing, unreadable or not a JSON object are skipped. A profile that is
not found in any file fails with exit code `10`.

```json
{
  "profiles": [
    {
      "default": {
        "elastic_host": "http://localhost:9200",
        "schema_db": "sqlite:///esmigrate.db",
        "schema_dir": "./migrations"
      }
    },
    {
      "production": {
        "elastic_host": "https://es.example.com:9200",
        "elastic_api_key": "${ESMIGRATE_ES_API_KEY}",
        "schema_db": "postgresql://migrator:${ESMIGRATE_DB_PASSWORD}@db.example.com/platform",
        "schema_db_schema": "search_migrations",
        "schema_dir": "./migrations",
        "log_file": "/var/log/esmigrate/esmigrate.log"
      }
    }
  ]
}
```

Select a profile with `-p`/`--profile`; the default profile is called `default`.

```bash
esmigrate -p production upgrade
```

## Environment variables in values

Any string value, including values inside `elastic_headers`, may reference environment variables as `${NAME}`. This
keeps secrets and per-environment values out of `config.json`. A reference to a variable that is not set fails with
exit code `11` and names the variable and the field; it never turns into an empty string.

## Profile fields

`schema_dir` is required; every other field is optional. Invalid values fail when the profile is loaded, with exit code
`11`.

| Field | Default | Description |
|---|---|---|
| `schema_dir` | (required) | Directory containing the migration scripts. |
| `schema_ext` | `.esm` | Script file extension. |
| `schema_db` | `sqlite:///esmigrate.db` | SQLAlchemy URL of the schema version database. See [](databases.md). |
| `schema_db_schema` | none | PostgreSQL schema or MySQL database for the schema version tables. |
| `schema_namespace` | `default` | Separates the history of several projects stored in one database. |
| `lock_timeout` | `0` | Seconds to wait for the migration lock; `0` fails immediately. See [](locking.md). |
| `elastic_host` | `http://localhost:9200` | Elasticsearch URL (`http` or `https`); may include a path prefix. |
| `elastic_headers` | `{"Connection": "keep-alive"}` | Extra HTTP headers sent with every request. |
| `elastic_timeout` | `60` | Request timeout in seconds; `null` disables it. |
| `elastic_username` / `elastic_password` | none | Basic authentication. |
| `elastic_api_key` | none | Encoded API key, sent as `Authorization: ApiKey …`. |
| `elastic_ca_certs` | none | CA bundle used to verify the server certificate. |
| `elastic_verify_certs` | `true` | Set `false` to skip certificate verification (test clusters only). |
| `elastic_client_cert` | none | Client certificate (chain) for mutual TLS. |
| `elastic_client_key` | none | Private key, if not included in `elastic_client_cert`. |
| `elastic_client_key_password` | none | Passphrase of an encrypted private key. |
| `log_file` | none | Write a debug log file with an audit trail. See [](logging.md). |
| `log_rotation` | `size` | `size` rotates by size; `external` leaves rotation to logrotate. |
| `log_max_bytes` | `10485760` | Size limit for `size` rotation (10 MiB). |
| `log_backup_count` | `5` | Rotated files kept by `size` rotation. |

The `SCHEMA_PATTERN` environment variable overrides the script filename pattern; see [](scripts.md).

## Showing the configuration

`esmigrate config` prints the effective profile. Passwords, API keys, key passphrases, `Authorization` headers and the
password in `schema_db` are masked.
