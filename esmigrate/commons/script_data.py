from enum import StrEnum

from esmigrate.commons.helpers import make_sha1
from esmigrate.commons.mig_version import MigVersion


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"


class Operation(StrEnum):
    UP = "up"
    DOWN = "down"
    FORCE = "force"
    RESET = "reset"


class ScriptData:
    def __init__(
        self,
        version: MigVersion,
        name: str,
        extension: str,
        path: str,
        content: str,
        direction: Direction | None = None,
    ) -> None:
        self.version = version
        self.description = f"{name}.{extension}"
        self.path = path
        self.content = content
        self.checksum = make_sha1(content)
        self.direction = direction
