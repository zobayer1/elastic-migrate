# -*- coding: utf-8 -*-
import pytest
from click.testing import CliRunner

from esmigrate import cli


@pytest.fixture(scope='module')
def runner():
    return CliRunner()


@pytest.fixture(scope='module')
def defaults():
    return {
        'profile': 'dev'
    }


def test_cli(runner):
    result = runner.invoke(cli.main)
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_help(runner):
    result = runner.invoke(cli.main, ['--help'])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_version(runner):
    result = runner.invoke(cli.main, ['--version'])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_profile(runner, defaults):
    result = runner.invoke(cli.main, ['--profile', defaults['profile']])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_init_cmd(runner, defaults):
    result = runner.invoke(cli.main, ['init'])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults['profile'] in result.output.strip()


def test_cli_with_config_cmd(runner, defaults):
    result = runner.invoke(cli.main, ['config'])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults['profile'] in result.output.strip()


def test_cli_with_upgrade_cmd(runner, defaults):
    result = runner.invoke(cli.main, ['upgrade'])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults['profile'] in result.output.strip()


def test_cli_with_downgrade_cmd(runner, defaults):
    result = runner.invoke(cli.main, ['downgrade'])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults['profile'] in result.output.strip()


def test_cli_with_rollback_cmd(runner, defaults):
    result = runner.invoke(cli.main, ['rollback'])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults['profile'] in result.output.strip()


def test_cli_with_reset_cmd(runner, defaults):
    result = runner.invoke(cli.main, ['reset'])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults['profile'] in result.output.strip()
