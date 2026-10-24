import os
import signal
import subprocess
import sys

import pytest

from esmigrate.exceptions import Errors
from tests.integration.conftest import PROFILE
from tests.integration.test_migrations import CREATE_INDEX, doc_count, versions, write_schemas

CREATE_DOCUMENT = """PUT /{index}/_create/1?refresh=true
{"user": "alice"}
"""

HOLDER = """
import asyncio, sys
from esmigrate.internals import DBManager

async def main():
    async with DBManager.connect(sys.argv[1]) as db, db.lock():
        print("locked", flush=True)
        await asyncio.get_running_loop().run_in_executor(None, sys.stdin.read)

asyncio.run(main())
"""


@pytest.fixture
def isolated_env(tmp_path):
    """pytest fixture for subprocess environments that only see the integration config file"""
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")
    return env


@pytest.fixture
def lock_holder(db_url, isolated_env):
    """pytest fixture starting a separate process that holds the migration lock until released"""
    processes = []

    def start():
        process = subprocess.Popen(
            [sys.executable, "-c", HOLDER, db_url],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=isolated_env,
        )
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "locked"
        processes.append(process)
        return process

    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait()
        for stream in (process.stdin, process.stdout):
            if stream is not None and not stream.closed:
                stream.close()


def release(process):
    assert process.stdin is not None
    process.stdin.close()
    assert process.wait(timeout=30) == 0


def start_upgrade(tmp_path, env):
    return subprocess.Popen(
        [sys.executable, "-c", "from esmigrate.cli import main; main()", "--profile", PROFILE, "upgrade"],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_lock_held_by_another_process_blocks_upgrade(esmigrate, schema_dir, es, es_index, stored_rows, lock_holder):
    """Test fails if upgrade runs while another process holds the lock, or stays blocked after release"""
    write_schemas(schema_dir, es_index, {"V1_0__create.esm": CREATE_INDEX})
    holder = lock_holder()
    result = esmigrate("upgrade")
    assert result.exit_code == Errors.ERR_DB_LOCKED, result.output
    assert "Migration lock is held" in result.output
    assert stored_rows() == []
    release(holder)
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert versions(stored_rows()) == [("1.0", True)]


def test_concurrent_upgrades_apply_each_script_once(
    profile, schema_dir, es, es_index, stored_rows, lock_holder, tmp_path, isolated_env
):
    """Test fails if two upgrades racing for the lock both apply scripts or either one fails"""
    write_schemas(schema_dir, es_index, {"V1_0__create.esm": CREATE_INDEX, "V1_1__document.esm": CREATE_DOCUMENT})
    profile(lock_timeout=60)
    holder = lock_holder()
    runs = [start_upgrade(tmp_path, isolated_env) for _ in range(2)]
    release(holder)
    outputs = [run.communicate(timeout=120)[0] for run in runs]
    assert [run.returncode for run in runs] == [0, 0], outputs
    assert sum("Schema database upgraded to 1.1" in output for output in outputs) == 1
    assert sum("nothing to do" in output for output in outputs) == 1
    assert versions(stored_rows()) == [("1.0", True), ("1.1", True)]
    assert doc_count(es, es_index) == 1


def test_lock_of_killed_process_does_not_block(esmigrate, schema_dir, es, es_index, lock_holder):
    """Test fails if a lock left by a killed process blocks later runs"""
    write_schemas(schema_dir, es_index, {"V1_0__create.esm": CREATE_INDEX})
    holder = lock_holder()
    holder.send_signal(signal.SIGKILL)
    holder.wait()
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output


def test_audit_log_records_lock(esmigrate, profile, schema_dir, es_index, tmp_path):
    """Test fails if a real run does not record lock acquisition and release"""
    write_schemas(schema_dir, es_index, {"V1_0__create.esm": CREATE_INDEX})
    profile(log_file=str(tmp_path / "audit.log"))
    assert esmigrate("upgrade").exit_code == 0
    text = (tmp_path / "audit.log").read_text()
    assert "Migration lock acquired" in text
    assert "Migration lock released after" in text
