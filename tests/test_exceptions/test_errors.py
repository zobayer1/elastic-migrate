import json
import subprocess
import sys

import pytest

from esmigrate.exceptions import Errors

RESERVED_EXIT_CODES = {0, 1, 2, 126, 127}


def test_error_codes_are_unique():
    """Test fails if two error categories share an exit code"""
    assert len({int(code) for code in Errors}) == len(Errors)


@pytest.mark.parametrize("code", list(Errors))
def test_error_codes_fit_posix_exit_status(code):
    """Test fails if an exit code is outside 0-255, reserved by convention, or in the signal range"""
    assert 0 < code < 126
    assert code not in RESERVED_EXIT_CODES


def run_cli(tmp_path, *args, env=None):
    command = [sys.executable, "-c", "from esmigrate.cli import main; main()", *args]
    return subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, check=False)


def test_process_exit_status_matches_profile_not_found(tmp_path, monkeypatch):
    """Test fails if the real process exit status differs from Errors.ERR_PROFILE_NOT_FOUND"""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("ESMIGRATE_CONFIG", raising=False)
    result = run_cli(tmp_path, "--profile", "missing-profile", "config")
    assert result.returncode == Errors.ERR_PROFILE_NOT_FOUND


def test_process_exit_status_matches_invalid_configuration(tmp_path, monkeypatch):
    """Test fails if the real process exit status differs from Errors.ERR_INVALID_CONFIGURATION"""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"profiles": [{"broken": {"schema_dir": "s", "elastic_timeout": -1}}]}))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("ESMIGRATE_CONFIG", str(config))
    result = run_cli(tmp_path, "--profile", "broken", "config")
    assert result.returncode == Errors.ERR_INVALID_CONFIGURATION
    assert "elastic_timeout" in result.stdout


def test_process_exits_when_schema_dir_is_missing(tmp_path, monkeypatch):
    """Test fails if a profile without schema_dir does not exit with Errors.ERR_INVALID_CONFIGURATION"""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"profiles": [{"noschema": {"schema_db": "sqlite:///x.db"}}]}))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("ESMIGRATE_CONFIG", str(config))
    result = run_cli(tmp_path, "--profile", "noschema", "init")
    assert result.returncode == Errors.ERR_INVALID_CONFIGURATION
    assert "schema_dir is required in profile 'noschema'" in result.stdout
