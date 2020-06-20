# -*- coding: utf-8 -*-
import json

from validator_collection import validators
from validator_collection.errors import InvalidURLError, EmptyValueError


def is_valid_json(content: str) -> bool:
    try:
        json.loads(content.strip())
        return True
    except ValueError:
        return False


def is_valid_ndjson(content: str) -> bool:
    for line in content.strip().split('\n'):
        if not is_valid_json(line):
            return False
    return True


def is_valid_path(base: str, *paths: str) -> bool:
    path_components = [base] + list(paths)
    path_url = '/'.join(p.strip('/') for p in path_components)
    try:
        validators.url(path_url, allow_special_ips=True)
        return True
    except (EmptyValueError, InvalidURLError):
        return False
