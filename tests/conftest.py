import logging

import pytest

from esmigrate.commons.log_setup import CONSOLE_HANDLER, FILE_HANDLER, LOGGER_NAME, remove_handlers


@pytest.fixture(autouse=True)
def reset_esmigrate_logging():
    """pytest fixture closing esmigrate log handlers after each test so no file stays open"""
    yield
    logger = logging.getLogger(LOGGER_NAME)
    remove_handlers(logger, CONSOLE_HANDLER)
    remove_handlers(logger, FILE_HANDLER)
