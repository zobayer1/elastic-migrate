import json
from hashlib import sha1


def is_valid_json(content: str) -> bool:
    try:
        json.loads(content.strip())
        return True
    except ValueError:
        return False


def is_valid_ndjson(content: str) -> bool:
    return all(is_valid_json(line) for line in content.strip().split("\n"))


def make_sha1(s: str, encoding: str = "utf-8") -> bytes:
    return sha1(s.encode(encoding)).digest()
