# Quickstart

This walkthrough creates an index with a first migration, using SQLite for the schema version history.

## 1. Write a configuration file

Create `config.json` in your project directory:

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

`esmigrate config` shows the loaded settings, with secrets masked.

## 2. Write a migration script

Create `migrations/V1_0__create_tweets_index.esm`:

```text
PUT /tweets
{
  "settings": {"number_of_shards": 1, "number_of_replicas": 0},
  "mappings": {"properties": {"user": {"type": "keyword"}, "message": {"type": "text"}}}
}
```

A script is a list of requests: a line with an HTTP verb and a path, optionally followed by a JSON or NDJSON body. See
[](scripts.md) for the full format.

## 3. Run it

```bash
esmigrate init
esmigrate upgrade
```

`init` creates the schema version table. `upgrade` runs every script that has not been applied yet, in version order,
and records each run. Running `upgrade` again does nothing until you add a script with a higher version, such as
`V1_1__index_first_tweet.esm`.

## Next steps

- Use a profile per environment and keep secrets in environment variables: [](configuration.md).
- Connect to a secured Elasticsearch 8 cluster: [](security.md).
- Store the history in PostgreSQL or MySQL: [](databases.md).
