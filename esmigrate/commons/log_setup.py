import logging
import sys
import time
from logging.handlers import RotatingFileHandler, WatchedFileHandler

from esmigrate.exceptions import InvalidConfigurationError

LOGGER_NAME = "esmigrate"
CONSOLE_HANDLER = "esmigrate-console"
FILE_HANDLER = "esmigrate-file"
FILE_FORMAT = "%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s %(message)s"
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5
LOG_ROTATIONS = ("size", "external")


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        return message if record.levelno < logging.WARNING else f"{record.levelname}: {message}"


def remove_handlers(logger: logging.Logger, name: str) -> None:
    for handler in [h for h in logger.handlers if h.get_name() == name]:
        logger.removeHandler(handler)
        handler.close()


def configure_console(level: int) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    remove_handlers(logger, CONSOLE_HANDLER)
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(CONSOLE_HANDLER)
    handler.setLevel(level)
    handler.setFormatter(ConsoleFormatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def configure_file(
    path: str | None,
    rotation: str = "size",
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    remove_handlers(logger, FILE_HANDLER)
    if path is None:
        return
    try:
        handler: logging.Handler = (
            WatchedFileHandler(path, encoding="utf-8")
            if rotation == "external"
            else RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        )
    except OSError as err:
        raise InvalidConfigurationError(f"Cannot open log file {path}: {err}") from err
    formatter = logging.Formatter(FILE_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime
    handler.set_name(FILE_HANDLER)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
