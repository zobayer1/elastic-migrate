# -*- coding: utf-8 -*-
import pytest

from esmigrate.contexts.context_config import ContextConfig
from esmigrate.utils import title, version, version_short, ScriptParser


@pytest.fixture(scope='module')
def context():
    return ContextConfig().load_for('test')


@pytest.fixture(scope='module')
def parser(context):
    return ScriptParser(context)


def test_script_parser_initialized(parser):
    assert parser.get_ctx_profile() == 'test'


def test_script_parser_verbs(parser):
    assert {'DELETE', 'GET', 'POST', 'PUT'}.issubset(set(parser.verbs))


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


def test_version():
    assert version and len(version) > 0


def test_version_short():
    assert version_short and len(version_short) > 0
    assert version_short in version


def test_title():
    assert title and len(title) > 0
