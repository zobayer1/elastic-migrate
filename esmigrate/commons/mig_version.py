import re
from dataclasses import dataclass
from typing import Self

MIN_VERSION_PART = 0
MAX_VERSION_PART = 2147483647


def parse_version(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)(?:\.(\d+))?", text.strip())
    if m is None:
        raise ValueError(f"Invalid version: {text}")
    return int(m.group(1)), int(m.group(2) or 0)


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
