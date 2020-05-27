import pytest
from click.testing import CliRunner
from esmigrate import cli
from setuptools_scm import get_version


@pytest.fixture
def runner():
    return CliRunner()


def test_cli(runner):
    result = runner.invoke(cli.main)
    assert result.exit_code == 0
    assert not result.exception
    print(result.output.strip())
    assert result.output.strip() == get_version(root='..', relative_to=__file__)
