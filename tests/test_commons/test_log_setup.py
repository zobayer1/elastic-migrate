import logging
import re
from logging.handlers import RotatingFileHandler, WatchedFileHandler

import pytest

from esmigrate.commons.log_setup import (
    CONSOLE_HANDLER,
    FILE_HANDLER,
    LOGGER_NAME,
    ConsoleFormatter,
    configure_console,
    configure_file,
)
from esmigrate.exceptions import InvalidConfigurationError


def console_handlers():
    return [h for h in logging.getLogger(LOGGER_NAME).handlers if h.get_name() == CONSOLE_HANDLER]


def test_configure_console_replaces_previous_handler():
    """Test fails if configuring the console twice installs two handlers and duplicates every line"""
    configure_console(logging.INFO)
    configure_console(logging.DEBUG)
    handlers = console_handlers()
    assert len(handlers) == 1
    assert handlers[0].level == logging.DEBUG
    assert logging.getLogger(LOGGER_NAME).propagate is False


@pytest.mark.parametrize(
    ("level", "expected"),
    [(logging.DEBUG, "msg"), (logging.INFO, "msg"), (logging.WARNING, "WARNING: msg"), (logging.ERROR, "ERROR: msg")],
)
def test_console_formatter_prefixes_warnings_and_errors(level, expected):
    """Test fails if INFO output gains a prefix or WARNING/ERROR output loses its level prefix"""
    record = logging.LogRecord(LOGGER_NAME, level, __file__, 1, "msg", None, None)
    assert ConsoleFormatter("%(message)s").format(record) == expected


def file_handlers():
    return [h for h in logging.getLogger(LOGGER_NAME).handlers if h.get_name() == FILE_HANDLER]


def test_configure_file_writes_utc_debug_records(tmp_path):
    """Test fails if the log file does not record DEBUG lines with UTC ISO-8601 timestamps"""
    path = tmp_path / "esmigrate.log"
    configure_file(str(path))
    logging.getLogger(f"{LOGGER_NAME}.test").debug("audit line")
    file_handlers()[0].flush()
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z DEBUG esmigrate\.test audit line\n", path.read_text()
    )


def test_configure_file_none_removes_and_closes_handler(tmp_path):
    """Test fails if configuring no log file keeps writing to a previously configured one"""
    configure_file(str(tmp_path / "first.log"))
    handler = file_handlers()[0]
    assert isinstance(handler, RotatingFileHandler)
    configure_file(None)
    assert file_handlers() == []
    assert handler.stream is None


def test_size_rotation_keeps_backups(tmp_path):
    """Test fails if size rotation does not roll the file over and keep the configured number of backups"""
    path = tmp_path / "esmigrate.log"
    configure_file(str(path), rotation="size", max_bytes=200, backup_count=2)
    logger = logging.getLogger(f"{LOGGER_NAME}.test")
    for index in range(40):
        logger.info(f"line {index:03d} with some padding to fill the file")
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["esmigrate.log", "esmigrate.log.1", "esmigrate.log.2"]
    assert isinstance(file_handlers()[0], RotatingFileHandler)


def test_external_rotation_reopens_file_moved_by_logrotate(tmp_path):
    """Test fails if external rotation keeps writing to a file renamed by logrotate"""
    path = tmp_path / "esmigrate.log"
    configure_file(str(path), rotation="external")
    logger = logging.getLogger(f"{LOGGER_NAME}.test")
    logger.info("before rotation")
    path.rename(tmp_path / "esmigrate.log.1")
    logger.info("after rotation")
    file_handlers()[0].flush()
    assert isinstance(file_handlers()[0], WatchedFileHandler)
    assert "after rotation" in path.read_text()
    assert "after rotation" not in (tmp_path / "esmigrate.log.1").read_text()


def test_configure_file_reports_unwritable_location(tmp_path):
    """Test fails if a log file in a missing directory is not reported as a configuration error"""
    with pytest.raises(InvalidConfigurationError, match="Cannot open log file"):
        configure_file(str(tmp_path / "missing" / "esmigrate.log"))
