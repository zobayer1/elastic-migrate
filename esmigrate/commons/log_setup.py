import logging
import sys

LOGGER_NAME = "esmigrate"
CONSOLE_HANDLER = "esmigrate-console"


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        return message if record.levelno < logging.WARNING else f"{record.levelname}: {message}"


def configure_console(level: int) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in [h for h in logger.handlers if h.get_name() == CONSOLE_HANDLER]:
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(CONSOLE_HANDLER)
    handler.setLevel(level)
    handler.setFormatter(ConsoleFormatter("%(message)s"))
    logger.addHandler(handler)
    return logger
