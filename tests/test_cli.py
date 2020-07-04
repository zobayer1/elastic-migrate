# -*- coding: utf-8 -*-
import pytest
from click.testing import CliRunner

from esmigrate import cli


@pytest.fixture(scope="module")
def runner():
    """pytest fixture for testing command line interfaces"""
    return CliRunner()


@pytest.fixture(scope="module")
def defaults():
    """pytest fixture for providing default profile name"""
    return {"profile": "dev"}


def test_cli_invocation_succeeds(runner):
    """Test fails `esmigrate` does not return with success"""
    result = runner.invoke(cli.main)
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_help_invocation_succeeds(runner):
    """Test fails `esmigrate --help` does not return with success"""
    result = runner.invoke(cli.main, ["--help"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_version_invocation_succeeds(runner):
    """Test fails `esmigrate --version` does not return with success"""
    result = runner.invoke(cli.main, ["--version"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_profile_invocation_succeeds(runner, defaults):
    """Test fails `esmigrate --profile dev` does not return with success"""
    result = runner.invoke(cli.main, ["--profile", defaults["profile"]])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()


def test_cli_with_init_cmd_invocation_succeeds(runner, defaults):
    """Test fails `esmigrate init` does not return with success"""
    result = runner.invoke(cli.main, ["init"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults["profile"] in result.output.strip()


def test_cli_with_config_cmd_invocation_succeeds(runner, defaults):
    """Test fails `esmigrate config` does not return with success"""
    result = runner.invoke(cli.main, ["config"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults["profile"] in result.output.strip()


def test_cli_with_upgrade_cmd_invocation_succeeds(runner, defaults):
    """Test fails `esmigrate upgrade` does not return with success"""
    result = runner.invoke(cli.main, ["upgrade"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults["profile"] in result.output.strip()


def test_cli_with_downgrade_cmd_invocation_succeeds(runner, defaults):
    """Test fails `esmigrate downgrade` does not return with success"""
    result = runner.invoke(cli.main, ["downgrade"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults["profile"] in result.output.strip()


def test_cli_with_rollback_cmd_invocation_succeeds(runner, defaults):
    """Test fails `esmigrate rollback` does not return with success"""
    result = runner.invoke(cli.main, ["rollback"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults["profile"] in result.output.strip()


def test_cli_with_reset_cmd_invocation_succeeds(runner, defaults):
    """Test fails `esmigrate reset` does not return with success"""
    result = runner.invoke(cli.main, ["reset"])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip()
    assert defaults["profile"] in result.output.strip()
