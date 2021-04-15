# -*- coding: utf-8 -*-
import pytest

from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    InvalidCommandScriptError,
    ContextObjectNotSetError,
    InvalidCommandVerbError,
    InvalidCommandPathError,
    InvalidCommandBodyError,
)
from esmigrate.internals import ScriptParser


@pytest.fixture(scope="module")
def script_parser():
    """pytest fixture for providing default ScriptParser object"""
    _parser = ScriptParser()
    _parser.init_ctx(ContextConfig())
    return _parser


@pytest.fixture(scope="function")
def parameter(request):
    """pytest fixture for allowing indirect pytest.mark.parametrize"""
    return request.param


@pytest.mark.parametrize(
    "parameter",
    ["no command", "no command\nGET path", "GET", "GETTING this"],
    indirect=["parameter"],
)
def test_script_parser_raises_invalid_command_script(script_parser, parameter):
    """Test fails if get_commands does not raise error for invalid command script"""
    with pytest.raises(InvalidCommandScriptError):
        for _ in script_parser.get_commands(parameter):
            pass


@pytest.mark.parametrize("parameter", ["GeT this", " delete this"], indirect=["parameter"])
def test_script_parser_raises_invalid_command_verb(script_parser, parameter):
    """Test fails if get_commands does not raise error for invalid command verb"""
    with pytest.raises(InvalidCommandVerbError):
        for _ in script_parser.get_commands(parameter):
            pass


@pytest.mark.parametrize(
    "parameter",
    ["GET http://localhost:9200/twitter?size=100&text=this is me&page=1"],
    indirect=["parameter"],
)
def test_script_parser_raises_invalid_command_path(script_parser, parameter):
    """Test fails if get_commands does not raise error for invalid command path"""
    with pytest.raises(InvalidCommandPathError):
        for _ in script_parser.get_commands(parameter):
            pass


@pytest.mark.parametrize(
    "parameter",
    [
        "GET /twitter/_search?size=100\n{'not valid'}",
        "GET /twitter/_search?size=100\n{'not valid 1'}\n{'not valid 2'}\n",
    ],
    indirect=["parameter"],
)
def test_script_parser_raises_invalid_command_body(script_parser, parameter):
    """Test fails if get_commands does not raise error for invalid command body"""
    with pytest.raises(InvalidCommandBodyError):
        for _ in script_parser.get_commands(parameter):
            pass


@pytest.mark.parametrize(
    "parameter",
    [
        "GET path",
        "DELETE path?len=0",
        "          \t POST  \tpath/to/happiness  \t   ",
        '\n  \n\n\t  PUT  /path/surrounded/by/slash/?and=more&plus="a few more"  \n \t\t\n\r',
        "GET twitter/_search\n{}",
        'GET twitter/_search\n{"query": {}}',
        'GET twitter/_search\n{"query1": {}}\n{"query2": {}}\n{"query3": {}}',
    ],
    indirect=["parameter"],
)
def test_script_parser_with_single_command(script_parser, parameter):
    """Test fails if get_commands cannot process script with single valid command"""
    commands = [command for command in script_parser.get_commands(parameter)]
    assert len(commands) == 1


def test_script_parser_raises_context_object_not_set_error():
    """Test fails if get_commands does not raise error when called without a context"""
    with pytest.raises(ContextObjectNotSetError):
        for _ in ScriptParser().get_commands(""):
            pass
