import re
from collections.abc import Iterator
from urllib.parse import urlparse

from esmigrate.commons import (
    JSON_HEADER,
    NDJSON_HEADER,
    Command,
    http_verbs,
    is_valid_json,
    is_valid_ndjson,
)
from esmigrate.exceptions import (
    InvalidCommandBodyError,
    InvalidCommandPathError,
    InvalidCommandScriptError,
    InvalidCommandVerbError,
)


class ScriptParser:
    def __init__(self) -> None:
        self._pattern = re.compile(rf"^({'|'.join(http_verbs)})\s+(.*)$", re.M | re.I)

    def get_commands(self, script_text: str) -> Iterator[Command]:
        stripped_lines = [line.strip() for line in script_text.split("\n") if len(line.strip()) > 0]
        if not stripped_lines:
            raise InvalidCommandScriptError("Script does not contain any command")
        matches = [(idx, m) for idx, line in enumerate(stripped_lines) if (m := self._pattern.match(line))]
        if not matches or matches[0][0] != 0:
            raise InvalidCommandScriptError(f"Unexpected command found: {stripped_lines[0].split()[0]}")

        occurs = [idx for idx, _ in matches] + [len(stripped_lines)]
        for idx, (cmdline, m) in enumerate(matches):
            verb, path = m.group(1).strip(), m.group(2).strip()

            if verb not in http_verbs:
                raise InvalidCommandVerbError(f"Unexpected verb found: {verb}")

            parsed_path = urlparse(path)
            if parsed_path.scheme or parsed_path.netloc:
                raise InvalidCommandPathError(f"Unexpected URL scheme found: {path}")

            path = "/" + path.lstrip("/")
            cmdnext = occurs[idx + 1]

            if cmdline + 1 >= cmdnext:
                body, head = None, None
            else:
                body = "\n".join(stripped_lines[cmdline + 1 : cmdnext])
                if is_valid_json(body):
                    head = JSON_HEADER
                elif is_valid_ndjson(body):
                    head = NDJSON_HEADER
                else:
                    raise InvalidCommandBodyError(f"Expected a {JSON_HEADER} or {NDJSON_HEADER} body")

            yield Command(verb, path, body, head)
