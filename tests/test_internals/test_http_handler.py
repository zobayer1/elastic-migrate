# -*- coding: utf-8 -*-
import pytest

from esmigrate.commons import Command
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidCommandVerbError
from esmigrate.internals.http_handler import HTTPHandler


@pytest.fixture(scope='module')
def context():
    return ContextConfig().load_for('test')


@pytest.fixture(scope='module')
def http_handler(context):
    _handler = HTTPHandler()
    _handler.init_ctx(context)
    return _handler


def test_http_handler_initialized(http_handler):
    assert http_handler.get_ctx()
    assert http_handler.get_ctx().profile == 'test'


def test_http_handler_raises_context_not_set():
    _handler = HTTPHandler()
    _command = Command('PUT', 'twitter')
    with pytest.raises(ContextObjectNotSetError):
        _handler.make_requests(_command)


def test_http_handler_succeeds_get(http_handler):
    _command = Command('GET', 'twitter')
    assert http_handler.make_requests(_command) == 'GET'


def test_http_handler_succeeds_put(http_handler):
    _command = Command('PUT', 'twitter')
    assert http_handler.make_requests(_command) == 'PUT'


def test_http_handler_succeeds_post(http_handler):
    _command = Command('POST', 'twitter')
    assert http_handler.make_requests(_command) == 'POST'


def test_http_handler_succeeds_delete(http_handler):
    _command = Command('DELETE', 'twitter')
    assert http_handler.make_requests(_command) == 'DELETE'


def test_http_handler_raises_invalid_command_verb_error(http_handler):
    _command = Command('INVALID', 'twitter')
    with pytest.raises(InvalidCommandVerbError):
        http_handler.make_requests(_command)
