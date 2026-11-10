from dataclasses import dataclass, field

JSON_HEADER = {"Content-Type": "application/json"}
NDJSON_HEADER = {"Content-Type": "application/x-ndjson"}
http_verbs = ["GET", "PUT", "POST", "DELETE"]


@dataclass
class Command:
    verb: str
    path: str
    body: str | None = None
    head: dict[str, str] = field(default_factory=dict[str, str])
