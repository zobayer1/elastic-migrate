import asyncio
import functools
import getpass
import logging
import socket
import sys
import time
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Concatenate, NoReturn, ParamSpec, TypeVar

import click

from esmigrate.commons import configure_file, version
from esmigrate.contexts import ContextConfig, mask_db_url
from esmigrate.exceptions import (
    Errors,
    InvalidConfigurationError,
    InvalidDBConnectionError,
    InvalidSchemaTableError,
    LegacySchemaTableError,
    MigrationLockedError,
    SchemaVersionSqlDbError,
    UserProfileNotFoundError,
)
from esmigrate.internals import DBManager

log = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")
PROFILE_KEY = "esmigrate.profile"
LOG_FILE_KEY = "esmigrate.log_file"

DB_ERRORS: dict[type[Exception], Errors] = {
    InvalidDBConnectionError: Errors.ERR_DB_CONNECTION_FAILED,
    InvalidSchemaTableError: Errors.ERR_DB_LEGACY_TABLE,
    LegacySchemaTableError: Errors.ERR_DB_LEGACY_TABLE,
    MigrationLockedError: Errors.ERR_DB_LOCKED,
    SchemaVersionSqlDbError: Errors.ERR_DB_IN_ERROR_STATE,
}


def fail(err: Exception, code: int) -> int:
    log.error(f"{type(err).__name__}: {err}")
    return code


def run(coro: Coroutine[Any, Any, int]) -> NoReturn:
    code = asyncio.run(coro)
    log.debug(f"Finished {click.get_current_context().info_name} with exit code {code}")
    sys.exit(code)


@asynccontextmanager
async def hold_lock(cfg: ContextConfig, db: DBManager) -> AsyncGenerator[None, None]:
    log.debug(f"Acquiring migration lock for namespace {cfg.schema_namespace} (timeout {cfg.lock_timeout}s)")
    async with db.lock(cfg.lock_timeout):
        acquired = time.perf_counter()
        log.debug("Migration lock acquired")
        try:
            yield
        finally:
            log.debug(f"Migration lock released after {int((time.perf_counter() - acquired) * 1000)} ms")


def connect_db(cfg: ContextConfig, upgrade: bool = False) -> AbstractAsyncContextManager[DBManager]:
    return DBManager.connect(
        cfg.schema_db, namespace=cfg.schema_namespace, upgrade=upgrade, schema=cfg.schema_db_schema
    )


def load_config(ctx: click.Context) -> ContextConfig:
    profile: str = ctx.meta[PROFILE_KEY]
    log_file: str | None = ctx.meta[LOG_FILE_KEY]
    log.info(f"Loading profile: {profile}...")
    try:
        cfg = ContextConfig().load_for(profile)
    except UserProfileNotFoundError as err:
        sys.exit(fail(err, Errors.ERR_PROFILE_NOT_FOUND))
    except InvalidConfigurationError as err:
        sys.exit(fail(err, Errors.ERR_INVALID_CONFIGURATION))
    try:
        configure_file(log_file or cfg.log_file, cfg.log_rotation, cfg.log_max_bytes, cfg.log_backup_count)
    except InvalidConfigurationError as err:
        sys.exit(fail(err, Errors.ERR_INVALID_CONFIGURATION))
    log.info(f"Profile loaded: {profile}")
    log.debug(
        f"esmigrate {version} {ctx.info_name}: profile={profile} namespace={cfg.schema_namespace} "
        f"elastic_host={cfg.es_host} schema_db={mask_db_url(cfg.schema_db)} schema_db_schema={cfg.schema_db_schema} "
        f"user={getpass.getuser()} "
        f"host={socket.gethostname()}"
    )
    if not cfg.es_verify_certs:
        log.warning(
            "TLS certificate verification is disabled (elastic_verify_certs: false), "
            "connections to Elasticsearch are not authenticated"
        )
    return cfg


def pass_config(command: Callable[Concatenate[ContextConfig, P], R]) -> Callable[P, R]:
    @functools.wraps(command)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return command(load_config(click.get_current_context()), *args, **kwargs)

    return wrapper
