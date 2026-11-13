import json
import re
from collections.abc import Iterator
from urllib.parse import urlparse

from esmigrate.commons import (
    JSON_HEADER,
    NDJSON_HEADER,
    Command,
    http_verbs,
    http_verbs_text,
)
from esmigrate.exceptions import (
    InvalidCommandBodyError,
    InvalidCommandPathError,
    InvalidCommandScriptError,
    InvalidCommandVerbError,
)


def is_valid_json(content: str) -> bool:
    """Tell whether text is one JSON document"""
    try:
        json.loads(content.strip())
        return True
    except ValueError:
        return False


def is_valid_ndjson(content: str) -> bool:
    """Tell whether every line of text is a JSON document"""
    return all(is_valid_json(line) for line in content.strip().split("\n"))


class ScriptParser:
    """Parser of Kibana-console-style migration scripts"""

    def __init__(self) -> None:
        self._pattern = re.compile(rf"^({'|'.join(http_verbs)})\s+(.*)$", re.M | re.I)

    def get_commands(self, script_text: str) -> Iterator[Command]:
        """Yield the requests of a script, each with its body and content type"""
        stripped_lines = [line.strip() for line in script_text.split("\n") if len(line.strip()) > 0]
        if not stripped_lines:
            raise InvalidCommandScriptError("Script has no requests")
        matches = [(idx, m) for idx, line in enumerate(stripped_lines) if (m := self._pattern.match(line))]
        if not matches or matches[0][0] != 0:
            raise InvalidCommandScriptError(
                f"Script must start with a {http_verbs_text} line, found {stripped_lines[0].split()[0]!r}"
            )

        occurs = [idx for idx, _ in matches] + [len(stripped_lines)]
        for idx, (cmdline, m) in enumerate(matches):
            verb, path = m.group(1).strip(), m.group(2).strip()

            if verb not in http_verbs:
                raise InvalidCommandVerbError(f"Unsupported verb {verb!r}, use {http_verbs_text}")

            parsed_path = urlparse(path)
            if parsed_path.scheme or parsed_path.netloc:
                raise InvalidCommandPathError(f"Absolute URL not allowed: {path!r}, use a path such as /index")

            path = "/" + path.lstrip("/")
            cmdnext = occurs[idx + 1]

            if cmdline + 1 >= cmdnext:
                body, head = None, {}
            else:
                body = "\n".join(stripped_lines[cmdline + 1 : cmdnext]) + "\n"
                if is_valid_json(body):
                    head = JSON_HEADER
                elif is_valid_ndjson(body):
                    head = NDJSON_HEADER
                else:
                    raise InvalidCommandBodyError("Body is neither valid JSON nor NDJSON")

            yield Command(verb, path, body, head)
