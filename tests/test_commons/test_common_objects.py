# -*- coding: utf-8 -*-
import pytest

from esmigrate.commons import Command, JSON_HEADER, NDJSON_HEADER, version, version_short, title, Header


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


def test_verb_was_set(command, verb):
    assert command.verb == verb


def test_path_was_set(command, path):
    assert command.path == path


def test_body_was_set(command, body):
    assert command.body == body


def test_head_for_valid_header_types(verb, path, body):
    _command = Command(verb, path, body)
    _command.head = JSON_HEADER.dict()
    assert Header(_command.head).is_json_header()
    _command.head = NDJSON_HEADER.dict()
    assert Header(_command.head).is_ndjson_header()


def test_repr_outputs_string(command, verb, path):
    repr_text = repr(command)
    assert len(repr_text) > 0
    assert verb in repr_text
    assert path in repr_text
    assert 'header' in repr_text


def test_version_string_not_empty():
    assert version and len(version) > 0


def test_version_short_is_substring_of_version():
    assert version_short and len(version_short) > 0
    assert version_short in version


def test_title_string_not_empty():
    assert title and len(title) > 0
