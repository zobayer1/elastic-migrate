# -*- coding: utf-8 -*-
import json

import pytest

from esmigrate.commons import Command


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


def test_repr(command, verb, path, body):
    repr_text = repr(command)
    assert len(repr_text) > 0
    assert verb in repr_text
    assert path in repr_text
    assert json.dumps(body, indent=2) in repr_text
