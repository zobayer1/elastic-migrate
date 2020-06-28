# -*- coding: utf-8 -*-
import pytest
from requests import HTTPError

from esmigrate.commons import Command
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import ContextObjectNotSetError, InvalidCommandVerbError
from esmigrate.internals import HTTPHandler


@pytest.fixture(scope='module')
def http_handler():
    _ctx = ContextConfig().load_for('test')
    _ctx.headers = {'header_key': 'header_value'}
    _handler = HTTPHandler()
    _handler.init_ctx(_ctx)
    return _handler


def test_http_handler_initialized_with_test_context(http_handler):
    assert http_handler.get_ctx().profile == 'test'


def test_http_handler_raises_invalid_command_verb_error(http_handler):
    with pytest.raises(InvalidCommandVerbError):
        http_handler.make_requests(Command('PATCH', 'http://example.com'))


def test_http_handler_succeeds_get(http_handler, requests_mock):
    requests_mock.get('http://example.com', text='ok', status_code=200)
    response = http_handler.make_requests(Command('GET', 'http://example.com'))
    assert response.status_code == 200
    assert response.text == 'ok'


def test_http_handler_succeeds_put(http_handler, requests_mock):
    requests_mock.put('http://example.com', text='updated', status_code=200)
    response = http_handler.make_requests(Command('PUT', 'http://example.com'))
    assert response.status_code == 200
    assert response.text == 'updated'


def test_http_handler_succeeds_post(http_handler, requests_mock):
    requests_mock.post('http://example.com', text='created', status_code=201)
    response = http_handler.make_requests(Command('POST', 'http://example.com'))
    assert response.status_code == 201
    assert response.text == 'created'


def test_http_handler_succeeds_delete(http_handler, requests_mock):
    requests_mock.delete('http://example.com', text='deleted', status_code=200)
    response = http_handler.make_requests(Command('DELETE', 'http://example.com'))
    assert response.status_code == 200
    assert response.text == 'deleted'


def test_http_handler_raises_http_error(http_handler, requests_mock):
    requests_mock.get('http://example.com', text='not found', status_code=404)
    with pytest.raises(HTTPError):
        http_handler.make_requests(Command('GET', 'http://example.com'))


def test_http_handler_raises_context_object_not_set_error():
    with pytest.raises(ContextObjectNotSetError):
        HTTPHandler().make_requests(Command('PUT', 'http://example.com'))
