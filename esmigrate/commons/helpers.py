import json
import os
import re


def is_valid_json(content: str) -> bool:
    try:
        json.loads(content.strip())
        return True
    except ValueError:
        return False


def is_valid_ndjson(content: str) -> bool:
    return all(is_valid_json(line) for line in content.strip().split("\n"))


def construct_path(base: str, *paths: str) -> str:
    return "/".join(p.strip("/") for p in (base, *paths))


def parse_file_path(path: str) -> tuple:
    base = os.path.basename(path)
    prefix = path[: -len(base) or None]
    extension = os.path.splitext(base)[1]
    filename = base[: -len(extension) or None]
    return prefix, filename, extension


def parse_version(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)(?:\.(\d+))?", text.strip())
    if m is None:
        raise ValueError(f"Invalid version: {text}")
    return int(m.group(1)), int(m.group(2) or 0)
