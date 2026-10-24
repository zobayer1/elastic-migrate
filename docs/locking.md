# Migration lock

`upgrade`, `rollback` and `reset` take a lock for the profile's database, schema and namespace before reading the
history and release it when they finish, also after errors. Two runs against the same history can therefore never apply
scripts at the same time; runs for different namespaces or schemas do not block each other.

| Database | Mechanism | After a crash |
|---|---|---|
| PostgreSQL | advisory lock | released when the connection closes |
| MySQL | `GET_LOCK` | released when the connection closes |
| SQLite | row in `esm_schema_lock` | taken over automatically when the holder's process no longer exists on the same machine; otherwise use `esmigrate unlock` |

## Waiting for the lock

By default a run fails immediately when the lock is held, with exit code `23` and a message naming the holder (host and
process on SQLite, the backend or connection ID on PostgreSQL and MySQL). Set `lock_timeout` to wait instead, for
example in pipelines that may overlap:

```json
{
  "profiles": [
    {
      "default": {
        "schema_db": "sqlite:///esmigrate.db",
        "schema_dir": "./migrations",
        "lock_timeout": 120
      }
    }
  ]
}
```

## Removing a stuck SQLite lock

If a run was killed on another machine, or on Windows where stale locks are not detected automatically, remove the lock
after making sure no run is active:

```bash
esmigrate unlock
```
