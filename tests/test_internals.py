# -*- coding: utf-8 -*-
import pytest

from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import InvalidCommandScript, ContextNotSet, InvalidCommandVerb, InvalidCommandPath
from esmigrate.internals import ScriptParser


@pytest.fixture(scope='module')
def context():
    return ContextConfig().load_for('test')


@pytest.fixture(scope='module')
def parser(context):
    _parser = ScriptParser()
    _parser.init_ctx(context)
    return _parser


def test_script_parser_initialized(parser):
    assert parser.get_ctx_profile() == 'test'


def test_script_parser_verbs(parser):
    assert {'DELETE', 'GET', 'POST', 'PUT'}.issubset(set(parser.verbs))


def test_script_parser_raises_context_not_set():
    parser = ScriptParser()
    with pytest.raises(ContextNotSet):
        for _ in parser.get_commands(''):
            pass


def test_script_parser_raises_invalid_command_script(parser):
    test_strings = [
        # no command here
        'no command',
        # has a command, but prefixed with bla bla
        'no command\nGET path'
        # just a command verb
        'GET'
    ]
    for test_str in test_strings:
        with pytest.raises(InvalidCommandScript):
            for _ in parser.get_commands(test_str):
                pass


def test_script_parser_raises_invalid_command_verb(parser):
    test_strings = [
        # not properly cased
        'GeT this'
        # properly cased prefix, but not a verb
        'GETTING this'
    ]
    for test_str in test_strings:
        with pytest.raises(InvalidCommandVerb):
            for _ in parser.get_commands(test_str):
                pass


def test_script_parser_raises_invalid_command_path(parser):
    test_strings = [
        # Should not contain a base URL
        'GET http://localhost:9200/twitter?size=100&text=this is me&page=1'
    ]
    for test_str in test_strings:
        with pytest.raises(InvalidCommandPath):
            for _ in parser.get_commands(test_str):
                pass


def test_script_parser_with_single_command(parser):
    test_strings = [
        # A very tiny command string
        'GET path',
        # A bit longer command string
        'DELETE path?len=0'
        # A string with a lot of spaces around
        '          \t POST  \tpath/to/happiness  \t   ',
        # A string with a lot of newlines around
        '\n  \n\n\t  PUT  /path/surrounded/by/slash/?and=more&plus="a few more"  \n \t\t\n\r'
    ]
    for test_str in test_strings:
        commands = [command for command in parser.get_commands(test_str)]
        assert len(commands) == 1
