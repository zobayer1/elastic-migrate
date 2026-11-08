from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from esmigrate.commons.helpers import make_sha1, parse_version

MIN_VERSION_PART = 0
MAX_VERSION_PART = 2147483647


@dataclass(frozen=True, order=True)
class MigVersion:
    base: int
    rank: int

    def __post_init__(self) -> None:
        if (
            self.base < MIN_VERSION_PART
            or self.base > MAX_VERSION_PART
            or self.rank < MIN_VERSION_PART
            or self.rank > MAX_VERSION_PART
        ):
            raise ValueError(
                f"Schema version {self.base}.{self.rank} is out of range: [{MIN_VERSION_PART}, {MAX_VERSION_PART}]"
            )

    def __str__(self) -> str:
        return f"{self.base}.{self.rank}"

    @classmethod
    def parse(cls, text: str) -> Self:
        base, rank = parse_version(text)
        return cls(base, rank)


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"


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
