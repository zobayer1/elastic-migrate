import json
import os


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
