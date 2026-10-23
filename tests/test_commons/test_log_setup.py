import logging

import pytest

from esmigrate.commons.log_setup import CONSOLE_HANDLER, LOGGER_NAME, ConsoleFormatter, configure_console


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
