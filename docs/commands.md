# Commands

```text
esmigrate [OPTIONS] COMMAND [ARGS]...
```

## Global options

| Option | Description |
|---|---|
| `-p`, `--profile NAME` | Profile to load (default `default`). |
| `-v`, `--verbose` | Show debug output, including one line per Elasticsearch request. |
| `-q`, `--quiet` | Show warnings and errors only. Cannot be combined with `--verbose`. |
| `--log-file FILE` | Write a debug log file, overriding the profile's `log_file`. |
| `--version` | Show the version. |
| `--help` | Show help; `esmigrate COMMAND --help` works without any configuration. |

Status messages go to standard error; standard output only carries real output (`config`, `--version`, the banner).

## `init`

Creates the schema version table if needed and reports the latest applied version. If it finds a table from
ElasticMigrate v1, it upgrades it to the current layout and keeps the old table as `esm_schema_version_v1_backup`. Every
other command refuses to run against a v1 table (exit code `22`). See [](databases.md).

## `config`

Prints the effective profile with secrets masked.

## `upgrade`

```text
esmigrate upgrade [-s VERSION]
```

Runs every pending script, in version order, up to the latest one or up to `-s/--schema-version` (for example
`-s 1.10`). Scripts at or below the latest recorded version are skipped. `upgrade` refuses to run while the latest
recorded script has failed (exit code `21`).

## `rollback`

Removes failed entries from the history so that `upgrade` can run again after you fix the script. It does not undo
changes in Elasticsearch: fix the cause, adjust the script if needed, then run `upgrade`.

## `reset`

Removes the whole history of the profile's namespace. Elasticsearch is not touched; the next `upgrade` runs every
script again.

## `unlock`

```text
esmigrate unlock [-y]
```

Removes a stuck SQLite migration lock left by a crashed run, after confirmation (`-y/--yes` skips it). PostgreSQL and
MySQL locks are released automatically and need no unlocking. See [](locking.md).

`upgrade`, `rollback` and `reset` hold the migration lock while they run.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success, including "nothing to do". |
| `2` | Invalid command-line usage. |
| `10` | Profile not found. |
| `11` | Invalid configuration (profile values, certificates, log file). |
| `20` | Schema database unreachable, unsupported or missing its schema. |
| `21` | Schema database error, or the latest script failed. |
| `22` | Schema version table uses the v1 layout; run `esmigrate init`. |
| `23` | Migration lock held by another run. |
| `30` | `schema_dir` is not a directory. |
| `31` | Script file name or content cannot be read or does not match the pattern. |
| `32` | Script cannot be parsed. |
| `40` | Invalid `--schema-version`. |
| `50` | Elasticsearch returned an error response. |
| `51` | Elasticsearch unreachable, timed out or failed TLS. |
