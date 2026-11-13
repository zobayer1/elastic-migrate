from unittest.mock import AsyncMock

import pytest

from esmigrate import cli
from esmigrate.exceptions import Errors
from tests.test_cli.helpers import (
    hold_lock,
    invoke,
    lock_rows,
)


def test_cli_unlock_with_yes_removes_stuck_lock(runner, context):
    """Test fails if unlock --yes does not remove a stuck SQLite lock"""
    hold_lock(context)
    result = invoke(runner, "unlock", "--yes")
    assert result.exit_code == 0
    assert "Removed the migration lock for namespace default" in result.output
    assert lock_rows(context) == []


@pytest.mark.parametrize(("answer", "remaining"), [("y\n", 0), ("n\n", 1)])
def test_cli_unlock_asks_for_confirmation(runner, context, answer, remaining):
    """Test fails if unlock does not confirm first, or removes the lock when the answer is no"""
    hold_lock(context)
    result = runner.invoke(cli.main, ["--profile", "test", "unlock"], input=answer)
    assert result.exit_code == 0
    assert "Remove the migration lock for namespace default?" in result.output
    assert len(lock_rows(context)) == remaining
    if remaining:
        assert "Unlock cancelled" in result.output


def test_cli_unlock_reports_when_no_lock_is_held(runner, context):
    """Test fails if unlock without a stuck lock does not say so"""
    result = invoke(runner, "unlock", "--yes")
    assert result.exit_code == 0
    assert "No migration lock is held for namespace default" in result.output


def test_cli_unlock_explains_server_database_locks(runner, context, mocker):
    """Test fails if unlock on PostgreSQL or MySQL does not explain that locks release automatically"""
    mocker.patch("esmigrate.internals.DBManager.force_unlock", AsyncMock(return_value=None))
    result = invoke(runner, "unlock", "--yes")
    assert result.exit_code == 0
    assert "released automatically when the holder exits" in result.output


def test_cli_unlock_reports_database_errors(runner, context):
    """Test fails if unlock does not report an invalid database URL"""
    context.schema_db = "oracle://user@host/db"
    assert invoke(runner, "unlock", "--yes").exit_code == Errors.ERR_DB_CONNECTION_FAILED
