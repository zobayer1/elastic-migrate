from dataclasses import dataclass, field

JSON_HEADER = {"Content-Type": "application/json"}
NDJSON_HEADER = {"Content-Type": "application/x-ndjson"}
http_verbs = ["GET", "PUT", "POST", "DELETE"]
http_verbs_text = f"{', '.join(http_verbs[:-1])} or {http_verbs[-1]}"


@dataclass
class Command:
    """One Elasticsearch request parsed from a migration script"""

    verb: str
    path: str
    body: str | None = None
    head: dict[str, str] = field(default_factory=dict[str, str])
