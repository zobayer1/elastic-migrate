import logging

import click

from esmigrate.cli.common import DB_ERRORS, connect_db, fail, help_option, hold_lock, pass_config, run
from esmigrate.contexts import ContextConfig

log = logging.getLogger(__name__)


@click.command()
@help_option
@pass_config
def reset(cfg: ContextConfig) -> None:
    """Forget the applied versions of the namespace"""
    run(run_reset(cfg))


async def run_reset(cfg: ContextConfig) -> int:
    try:
        async with connect_db(cfg) as db, hold_lock(cfg, db):
            await db.delete_all_schema()
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    log.info("Schema database reset")
    return 0
