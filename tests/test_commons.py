# -*- coding: utf-8 -*-
import json

import pytest

from esmigrate.commons import Command, JSON_HEADER, NDJSON_HEADER, is_valid_json, is_valid_ndjson, is_valid_path, \
    version, version_short, title


@pytest.fixture(scope='module')
def verb():
    return 'GET'


@pytest.fixture(scope='module')
def path():
    return '/twitter/_search?size=100'


@pytest.fixture(scope='module')
def body():
    return """
        {
            "query": {
                "match_all": {}
            }
        }
        """


@pytest.fixture(scope='module')
def command(verb, path, body):
    return Command(verb, path, body)


def test_verb(command, verb):
    assert command.verb == verb


def test_path(command, path):
    assert command.path == path


def test_body(command, body):
    assert command.body == body


def test_head(command):
    command.head = JSON_HEADER.dict()
    assert 'json' in json.dumps(command.head)
    command.head = NDJSON_HEADER.dict()
    assert 'x-ndjson' in json.dumps(command.head)


def test_repr(command, verb, path):
    repr_text = repr(command)
    assert len(repr_text) > 0
    assert verb in repr_text
    assert path in repr_text
    assert 'header' in repr_text


def test_is_valid_json_succeeds():
    test_string = """
        {
            "query": {"match_all": {}}
        }
        """
    assert is_valid_json(test_string)


def test_is_valid_json_fails():
    test_string = """
        {
            'query': {'match_all': {}}
        }
        """
    assert not is_valid_json(test_string)


def test_is_valid_ndjson_succeeds_single():
    test_string = """{"key": "value"}"""
    assert is_valid_ndjson(test_string)


def test_is_valid_ndjson_succeeds_multiple():
    test_string = """{"key1": "value1"}\n{"key2": "value2"}\n"""
    assert is_valid_ndjson(test_string)


def test_is_valid_ndjson_fails():
    test_string = """
        {
            "query": {"match_all": {}}
        }
        """
    assert not is_valid_ndjson(test_string)


def test_is_valid_path_succeeds():
    assert is_valid_path('http://192.168.5.127:9200', 'twitter/_search?size=100')


def test_is_valid_path_fails():
    assert not is_valid_path('just_a_string', 'which won\'t pass')


def test_version():
    assert version and len(version) > 0


def test_version_short():
    assert version_short and len(version_short) > 0
    assert version_short in version


def test_title():
    assert title and len(title) > 0
