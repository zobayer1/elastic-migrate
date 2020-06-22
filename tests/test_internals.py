# -*- coding: utf-8 -*-
import pytest

from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import InvalidCommandScript, ContextNotSet, InvalidCommandVerb, InvalidCommandPath, \
    InvalidCommandBody
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
    assert parser.get_ctx()
    assert parser.get_ctx().profile == 'test'


def test_script_parser_verbs(parser):
    assert {'DELETE', 'GET', 'POST', 'PUT'}.issubset(set(parser.verbs))


def test_script_parser_raises_context_not_set():
    parser = ScriptParser()
    with pytest.raises(ContextNotSet):
        for _ in parser.get_commands(''):
            pass


def test_script_parser_raises_invalid_command_script(parser):
    test_strings = [
        # No command here
        """no command""",
        # Has a command, but prefixed with bla bla
        """no command\nGET path""",
        # Just a command verb
        """GET""",
        # Properly cased prefix, but not a verb
        """GETTING this""",
    ]
    for test_str in test_strings:
        with pytest.raises(InvalidCommandScript):
            for _ in parser.get_commands(test_str):
                pass


def test_script_parser_raises_invalid_command_verb(parser):
    test_strings = [
        # Not properly cased
        """GeT this""",
    ]
    for test_str in test_strings:
        with pytest.raises(InvalidCommandVerb):
            for _ in parser.get_commands(test_str):
                pass


def test_script_parser_raises_invalid_command_path(parser):
    test_strings = [
        # Path contains base URL
        """GET http://localhost:9200/twitter?size=100&text=this is me&page=1""",
    ]
    for test_str in test_strings:
        with pytest.raises(InvalidCommandPath):
            for _ in parser.get_commands(test_str):
                pass


def test_script_parser_raises_invalid_command_body(parser):
    test_strings = [
        # Contains invalid JSON body
        """GET /twitter/_search?size=100\n{'not valid'}""",
        # Contains invalid NDJSON body
        """GET /twitter/_search?size=100\n{'not valid 1'}\n{'not valid 2'}\n""",
    ]
    for test_str in test_strings:
        with pytest.raises(InvalidCommandBody):
            for _ in parser.get_commands(test_str):
                pass


def test_script_parser_with_single_command(parser):
    test_strings = [
        # A very tiny command string
        """GET path""",
        # A bit longer command string
        """DELETE path?len=0""",
        # A string with a lot of spaces around
        """          \t POST  \tpath/to/happiness  \t   """,
        # A string with a lot of newlines around
        """\n  \n\n\t  PUT  /path/surrounded/by/slash/?and=more&plus="a few more"  \n \t\t\n\r""",
        # A valid command with an empty JSON body
        """GET twitter/_search\n{}""",
        # A valid command with a bigger JSON body
        """GET twitter/_search\n{"query": {}}""",
        # A valid command with an  NDJSON body
        """GET twitter/_search\n{"query1": {}}\n{"query2": {}}\n{"query3": {}}""",
    ]
    for test_str in test_strings:
        commands = [command for command in parser.get_commands(test_str)]
        assert len(commands) == 1
