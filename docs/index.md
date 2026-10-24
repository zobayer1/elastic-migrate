# ElasticMigrate

ElasticMigrate (`esmigrate`) applies versioned schema scripts to Elasticsearch and records every run in a SQL schema
version table, in the spirit of Flyway. It is built for unattended, repeatable deployments: scripts run strictly in
order, a failed script stops further migrations until it is resolved, concurrent runs are locked out, and every run can
leave an audit trail.

- Elasticsearch 8 over plain HTTP(S), with TLS, mutual TLS, basic authentication or API keys.
- Schema version history in SQLite, PostgreSQL or MySQL, optionally in a dedicated schema and namespace.
- A small CLI with predictable exit codes for CI pipelines and scheduled jobs.

```{toctree}
:maxdepth: 2
:caption: User guide

installation
quickstart
configuration
scripts
commands
security
databases
locking
logging
```
