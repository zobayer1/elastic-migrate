# Migration scripts

## File names

Scripts live in `schema_dir` and are named `V<version>_<sequence>__<description>.<extension>`, for example:

```text
V1_0__create_tweets_index.esm
V1_1__index_first_tweet.esm
V1_10__add_hashtags_field.esm
V2_0__reindex_tweets.esm
```

- `version` and `sequence` are whole numbers, compared numerically: `1.9` runs before `1.10`, and `9.1` before `10.1`.
  Each part may be at most `2147483647`.
- The description is made of letters, digits and underscores.
- Only files with the configured `schema_ext` (default `.esm`) are read. A file with that extension whose name does not
  match the pattern fails with exit code `31`, before anything runs.

The pattern can be replaced through the `SCHEMA_PATTERN` environment variable. It must define the named groups
`version`, `sequence`, `name` and `extension`; the default is:

```text
V(?P<version>[\d]+)_(?P<sequence>[\d]+)__(?P<name>[\w]+)\.(?P<extension>[\w]+)
```

## Script format

A script is a list of requests in the style of the Kibana console. Each request is a line with an HTTP verb and a path,
followed by an optional body:

```text
PUT /tweets/_mapping
{
  "properties": {"hashtags": {"type": "keyword"}}
}

POST /tweets/_bulk?refresh=true
{"index": {"_id": "1"}}
{"user": "alice", "message": "hello"}
{"index": {"_id": "2"}}
{"user": "bob", "message": "hi"}
```

- Verbs are `GET`, `PUT`, `POST` and `DELETE`, in upper case.
- Paths are relative to `elastic_host`, with or without a leading slash, and may carry a query string. Absolute URLs
  (`https://…`, `//host/…`) are rejected, so a script can never target another cluster.
- A body is either one JSON document (it may span several lines) or NDJSON, one JSON document per line, as used by
  `_bulk`. The `Content-Type` header follows the body, and every body is sent with a trailing newline.
- Blank lines are ignored. The first non-blank line must be a request line; scripts have no comment syntax.

## How scripts run

`upgrade` runs scripts in version order, one request at a time. If a request fails, the script is recorded as failed
with the responses so far, the remaining requests are skipped, and `upgrade` exits with code `50`. Further upgrades are
refused until the failure is resolved with `rollback` (see [](commands.md)). A script that cannot be parsed (an unknown
verb, an absolute URL or an invalid body) is recorded as failed in the same way, with exit code `32`. If Elasticsearch
cannot be reached, the run stops without recording the script.

The schema version table stores, per script, the version, description, file name relative to `schema_dir`, a SHA-1
checksum, the installing user, a UTC timestamp, the duration, the result and every request with its response. The
Elasticsearch host is never stored, so history stays valid when hosts move behind aliases or load balancers.
