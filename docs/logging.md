# Logging and audit trail

## Console

Status messages are written to standard error. `-v` adds one debug line per Elasticsearch request with its path, sizes,
status and duration; `-q` shows only warnings and errors.

## Log file

Set `log_file` in the profile, or pass `--log-file`, to write a log file. It always records debug detail with UTC
timestamps, whatever the console level:

```text
2026-10-23T21:26:11.776Z DEBUG esmigrate.cli esmigrate 2.0.0 upgrade: profile=default namespace=default ...
2026-10-23T21:26:11.801Z INFO esmigrate.cli Processing schema create_index.esm
2026-10-23T21:26:11.924Z DEBUG esmigrate.internals.http_handler PUT /tweets (40 bytes) -> 200 (71 bytes) in 122 ms
```

The audit trail contains:

- the run: version, command, profile, namespace, Elasticsearch host, schema database (password masked), operating system
  user and machine;
- the migration lock: acquired, released and how long it was held;
- each script: file, checksum, result and duration;
- each request: verb, path, request and response size, status and duration;
- the exit code.

Credentials, `Authorization` headers and request or response bodies are never logged.

## Rotation

| `log_rotation` | Behaviour |
|---|---|
| `size` (default) | Rotates at `log_max_bytes` (10 MiB) and keeps `log_backup_count` (5) old files. |
| `external` | Never rotates; reopens the file after an external tool such as logrotate moves it. |

Built-in `size` rotation is safe for one process per log file. When several runs may share a log file on the same
machine, give each job its own file (for example `"log_file": "/var/log/esmigrate/nightly.log"`) or use
`log_rotation: external` with logrotate:

```json
{
  "profiles": [
    {
      "default": {
        "schema_dir": "./migrations",
        "log_file": "/var/log/esmigrate/esmigrate.log",
        "log_rotation": "external"
      }
    }
  ]
}
```

```text
# /etc/logrotate.d/esmigrate
/var/log/esmigrate/esmigrate.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
}
```
