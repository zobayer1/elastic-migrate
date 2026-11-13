import logging
import sys

import click

from esmigrate.cli.common import DB_ERRORS, connect_db, fail, pass_config, run
from esmigrate.contexts import ContextConfig

log = logging.getLogger(__name__)


@click.command(help="Remove a stuck SQLite migration lock left by a crashed run")
@click.help_option(help="Show help index and exit")
@click.option("-y", "--yes", is_flag=True, help="Do not ask for confirmation")
@pass_config
def unlock(cfg: ContextConfig, yes: bool = False) -> None:
    if not yes and not click.confirm(f"Remove the migration lock for namespace {cfg.schema_namespace}?"):
        log.info("Unlock cancelled")
        sys.exit(0)
    run(run_unlock(cfg))


async def run_unlock(cfg: ContextConfig) -> int:
    try:
        async with connect_db(cfg) as db:
            removed = await db.force_unlock()
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    if removed is None:
        log.info("PostgreSQL and MySQL migration locks are released automatically when the holder exits")
    elif removed:
        log.info(f"Removed the migration lock for namespace {cfg.schema_namespace}")
    else:
        log.info(f"No migration lock is held for namespace {cfg.schema_namespace}")
    return 0
