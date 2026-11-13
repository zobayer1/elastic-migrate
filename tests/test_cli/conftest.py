import pytest
from click.testing import CliRunner

from esmigrate.contexts import ContextConfig
from tests.test_cli.helpers import ES_HOST


@pytest.fixture
def runner():
    """pytest fixture for testing command line interfaces"""
    return CliRunner()


@pytest.fixture
def schema_dir(tmp_path):
    """pytest fixture for providing an empty schema directory"""
    path = tmp_path / "schema_dir"
    path.mkdir()
    return path


@pytest.fixture
def context(tmp_path, schema_dir, mocker):
    """pytest fixture for a loaded test profile backed by a temporary SQLite database and a fake Elasticsearch"""
    ctx = ContextConfig()
    ctx.profile = "test"
    ctx.es_host = ES_HOST
    ctx.schema_db = f"sqlite:///{tmp_path / 'esmigrate.db'}"
    ctx.schema_dir = str(schema_dir)
    mocker.patch("esmigrate.contexts.ContextConfig.load_for", return_value=ctx)
    return ctx
