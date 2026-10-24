import httpx
from sqlalchemy import make_url

from esmigrate.exceptions import Errors


def test_elasticsearch_8_is_running(es_url):
    """Test fails if the compose elasticsearch service is not an 8.x cluster"""
    assert httpx.get(es_url, timeout=5).json()["version"]["number"].startswith("8.")


def test_init_creates_schema_table_on_each_backend(esmigrate):
    """Test fails if `esmigrate init` cannot create the schema table on SQLite, PostgreSQL or MySQL"""
    result = esmigrate("init")
    assert result.exit_code == 0, result.output
    assert "Schema version database initialized" in result.output
    assert esmigrate("init").exit_code == 0


def test_unreachable_database_reports_connection_error(esmigrate, profile, db_url, tmp_path):
    """Test fails if an unreachable database is not reported with the DB connection exit code"""
    url = make_url(db_url)
    if url.drivername == "sqlite":
        unreachable = f"sqlite:///{tmp_path / 'missing' / 'esmigrate.db'}"
    else:
        unreachable = url.set(host="127.0.0.1", port=1).render_as_string(hide_password=False)
    profile(schema_db=unreachable)
    result = esmigrate("init")
    assert result.exit_code == Errors.ERR_DB_CONNECTION_FAILED, result.output
    assert "InvalidDBConnectionError" in result.output
