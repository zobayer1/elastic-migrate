# -*- coding: utf-8 -*-
import pytest
import requests_mock
from requests import HTTPError

from esmigrate.commons import Command
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidCommandVerbError
from esmigrate.internals import HTTPHandler


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
    _command = Command('PUT', 'http://example.com')
    with pytest.raises(ContextObjectNotSetError):
        _handler.make_requests(_command)


@requests_mock.Mocker(kw='mock')
def test_http_handler_succeeds_get(http_handler, **kwargs):
    somehost = 'http://example.com'
    kwargs['mock'].get(somehost, json={'somekey': 'somevalue'})

    _command = Command('GET', somehost)
    response = http_handler.make_requests(_command)

    assert _command.verb == 'GET'
    assert response.ok
    assert response.json()['somekey'] == 'somevalue'


@requests_mock.Mocker(kw='mock')
def test_http_handler_succeeds_put(http_handler, **kwargs):
    somehost = 'http://example.com'
    kwargs['mock'].put(somehost, json={'somekey': 'somevalue'})

    _command = Command('PUT', somehost)
    response = http_handler.make_requests(_command)

    assert _command.verb == 'PUT'
    assert response.ok
    assert response.json()['somekey'] == 'somevalue'


@requests_mock.Mocker(kw='mock')
def test_http_handler_succeeds_post(http_handler, **kwargs):
    somehost = 'http://example.com'
    kwargs['mock'].post(somehost, json={'somekey': 'somevalue'})

    _command = Command('POST', somehost)
    response = http_handler.make_requests(_command)

    assert _command.verb == 'POST'
    assert response.ok
    assert response.json()['somekey'] == 'somevalue'


@requests_mock.Mocker(kw='mock')
def test_http_handler_succeeds_delete(http_handler, **kwargs):
    somehost = 'http://example.com'
    kwargs['mock'].delete(somehost, json={'somekey': 'somevalue'})

    _command = Command('DELETE', somehost)
    response = http_handler.make_requests(_command)

    assert _command.verb == 'DELETE'
    assert response.ok
    assert response.json()['somekey'] == 'somevalue'


def test_http_handler_raises_invalid_command_verb_error(http_handler):
    _command = Command('INVALID', 'http://example.com')
    with pytest.raises(InvalidCommandVerbError):
        http_handler.make_requests(_command)


def test_http_handler_sets_context_headers():
    somehost = 'http://example.com'
    with requests_mock.Mocker() as mock:
        mock.get(somehost, text='ok')
        ctx = ContextConfig()
        ctx.headers = {'somekey': 'somevalue'}
        http_handler = HTTPHandler(ctx)
        _command = Command('GET', somehost)
        response = http_handler.make_requests(_command)
        assert _command.head['somekey'] == 'somevalue'
        assert response.ok
        assert response.text == 'ok'


@requests_mock.Mocker(kw='mock')
def test_http_handler_raises_http_error(http_handler, **kwargs):
    somehost = 'http://example.com'
    kwargs['mock'].get(somehost, text='not found', status_code=404)
    _command = Command('GET', somehost)
    with pytest.raises(HTTPError):
        http_handler.make_requests(_command)
