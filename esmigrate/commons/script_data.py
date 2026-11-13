from enum import StrEnum
from hashlib import sha1

from esmigrate.commons.mig_version import MigVersion


def make_sha1(s: str, encoding: str = "utf-8") -> bytes:
    """Return the raw SHA-1 digest of the encoded text"""
    return sha1(s.encode(encoding)).digest()


class Direction(StrEnum):
    """Direction a script runs in, also its .up or .down file name segment"""

    UP = "up"
    DOWN = "down"


class Operation(StrEnum):
    """Operation recorded in a history row"""

    UP = "up"
    DOWN = "down"
    FORCE = "force"
    RESET = "reset"


class ScriptData:
    """One migration script file with its version, name, content and checksum"""

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
