# Security

## TLS

Use an `https` URL in `elastic_host`. The server certificate is verified against the system trust store, or against
`elastic_ca_certs` when set:

```json
{
  "profiles": [
    {
      "default": {
        "elastic_host": "https://es.example.com:9200",
        "elastic_ca_certs": "/etc/esmigrate/ca.crt",
        "elastic_username": "migrator",
        "elastic_password": "${ESMIGRATE_ES_PASSWORD}",
        "schema_dir": "./migrations"
      }
    }
  ]
}
```

`elastic_verify_certs: false` disables certificate verification. Use it only for test clusters: every run prints a
warning, and it cannot be combined with `elastic_ca_certs`. Certificate failures exit with code `51` and a message
starting with `TLS error`.

## Authentication

Choose one method per profile:

- **Basic authentication:** `elastic_username` and `elastic_password`, both required.
- **API key:** `elastic_api_key`, the `encoded` value returned by Elasticsearch when the key is created. It is sent as
  `Authorization: ApiKey <key>`.

Combining both, or adding an `Authorization` header in `elastic_headers` next to them, is a configuration error.
Credentials inside `elastic_host` (`https://user:pass@host`) are rejected; use the fields above. Rejected credentials
exit with code `50` (`401 Unauthorized`).

## Mutual TLS

For clusters that require client certificates, add `elastic_client_cert`, plus `elastic_client_key` when the key is a
separate file and `elastic_client_key_password` when it is encrypted:

```json
{
  "profiles": [
    {
      "default": {
        "elastic_host": "https://es.example.com:9200",
        "elastic_ca_certs": "/etc/esmigrate/ca.crt",
        "elastic_client_cert": "/etc/esmigrate/migrator.crt",
        "elastic_client_key": "/etc/esmigrate/migrator.key",
        "elastic_client_key_password": "${ESMIGRATE_KEY_PASSWORD}",
        "elastic_api_key": "${ESMIGRATE_ES_API_KEY}",
        "schema_dir": "./migrations"
      }
    }
  ]
}
```

Missing certificate files fail when the profile is loaded; unreadable certificates or a wrong passphrase fail before the
first request (both with exit code `11`).

## Keeping secrets out of files

Reference secrets as `${VARIABLE}` in any value and provide them through the environment of the run, for example from
your CI secret store. `esmigrate config` and the audit log mask passwords, API keys, key passphrases, `Authorization`
headers and the password in `schema_db`. Request and response bodies are never written to the log; they are stored in
the schema version history only.
