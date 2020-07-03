# -*- coding: utf-8 -*-
import json
import os


def is_valid_json(content: str) -> bool:
    try:
        json.loads(content.strip())
        return True
    except ValueError:
        return False


def is_valid_ndjson(content: str) -> bool:
    for line in content.strip().split("\n"):
        if not is_valid_json(line):
            return False
    return True


def construct_path(base: str, *paths: str) -> str:
    path_components = [base] + list(paths)
    return "/".join(p.strip("/") for p in path_components)


def parse_file_path(path: str) -> tuple:
    base = os.path.basename(path)
    prefix = path[: -len(base) or None]
    extension = os.path.splitext(base)[1]
    filename = base[: -len(extension) or None]
    return prefix, filename, extension
