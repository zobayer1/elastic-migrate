# -*- coding: utf-8 -*-
import json
import os
from urllib.parse import urlparse

from validator_collection import validators, checkers
from validator_collection.errors import InvalidURLError, EmptyValueError


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


def is_valid_url_path(base: str, *paths: str) -> bool:
    path_url = construct_path(base, *paths)
    try:
        validators.url(path_url, allow_special_ips=True)
        url_parsed = urlparse(path_url)
        return not checkers.is_url(url_parsed.path.strip("/"), allow_special_ips=True)
    except (EmptyValueError, InvalidURLError):
        return False


def parse_file_path(path: str) -> tuple:
    base = os.path.basename(path)
    prefix = path[: -len(base) or None]
    extension = os.path.splitext(base)[1]
    filename = base[: -len(extension) or None]
    return prefix, filename, extension
