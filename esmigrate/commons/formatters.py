import json
from datetime import UTC, datetime

from httpx import Response

from esmigrate.commons.command import Command


def query_results_string(command: Command, response: Response) -> str:
    return json.dumps(
        {
            "query": f"{command.verb} {command.path} {command.body}",
            "status": response.status_code,
            "result": response.text,
        }
    )


def query_error_string(command: Command, err: Exception) -> str:
    return json.dumps(
        {
            "query": f"{command.verb} {command.path} {command.body}",
            "status": None,
            "result": f"{type(err).__name__}: {err}",
        }
    )


def old_timestamp_to_utc(value: datetime | str | None, force_utc: bool = False) -> datetime | None:
    if value is None:
        return None
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    if stamp.tzinfo is None and force_utc:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)
