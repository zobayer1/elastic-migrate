import pytest


@pytest.fixture
def db_url(tmp_path):
    """pytest fixture for providing a file-backed SQLite URL in a temporary directory"""
    return f"sqlite:///{tmp_path / 'esmigrate.db'}"
