import logging

import click

from esmigrate.cli.common import DB_ERRORS, connect_db, fail, help_option, hold_lock, pass_config, run
from esmigrate.contexts import ContextConfig

log = logging.getLogger(__name__)


@click.command()
@help_option
@pass_config
def rollback(cfg: ContextConfig) -> None:
    """Revert to last successful schema version"""
    run(run_rollback(cfg))


async def run_rollback(cfg: ContextConfig) -> int:
    """Delete the failed state rows of the namespace"""
    try:
        async with connect_db(cfg) as db, hold_lock(cfg, db):
            latest = await db.find_latest_schema()
            if latest and not latest.success:
                log.info(f"Schema database has error entry for version {latest.version}")
                await db.delete_all_failed_schema()
                log.info("Rollback successful")
            else:
                log.info("Schema database does not have any error entry")
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    return 0
