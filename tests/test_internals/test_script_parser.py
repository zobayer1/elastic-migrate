import pytest

from esmigrate.exceptions import (
    InvalidCommandBodyError,
    InvalidCommandPathError,
    InvalidCommandScriptError,
    InvalidCommandVerbError,
)
from esmigrate.internals import ScriptParser


@pytest.fixture(scope="module")
def script_parser():
    """pytest fixture for providing default ScriptParser object"""
    return ScriptParser()


@pytest.fixture
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
    ["GET http://localhost:9200/twitter?size=100&text=this is me&page=1", "GET //es.example.com/twitter"],
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
    commands = list(script_parser.get_commands(parameter))
    assert len(commands) == 1


@pytest.mark.parametrize("parameter", ["", "  \n\t\n  "], indirect=["parameter"])
def test_script_parser_raises_invalid_command_script_for_empty_script(script_parser, parameter):
    """Test fails if get_commands does not raise a script error for empty scripts"""
    with pytest.raises(InvalidCommandScriptError, match="does not contain any command"):
        list(script_parser.get_commands(parameter))


@pytest.mark.parametrize(
    ("parameter", "expected"),
    [
        ("GET twitter/_search", "/twitter/_search"),
        ("GET /twitter/_search", "/twitter/_search"),
        ("GET twitter/", "/twitter/"),
        ("PUT /twitter/_doc/1?refresh=true", "/twitter/_doc/1?refresh=true"),
    ],
    indirect=["parameter"],
)
def test_script_parser_emits_host_relative_paths(script_parser, parameter, expected):
    """Test fails if get_commands does not produce a single leading-slash path without host"""
    assert next(script_parser.get_commands(parameter)).path == expected
