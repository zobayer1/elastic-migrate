import logging

import click

from esmigrate.cli.common import DB_ERRORS, connect_db, fail, pass_config, run
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import Errors, InvalidDBConnectionError
from esmigrate.internals import LEGACY_TABLE, Layout, create_tables_sql

log = logging.getLogger(__name__)


@click.command(help="Create the schema tables, copying rows from v1 and v2 tables if present")
@click.help_option(help="Show help index and exit")
@click.option("--print-sql", is_flag=True, help="Print the SQL that creates the schema tables, without connecting")
@pass_config
def init(cfg: ContextConfig, print_sql: bool = False) -> None:
    run(print_tables_sql(cfg) if print_sql else run_init(cfg))


async def run_init(cfg: ContextConfig) -> int:
    log.info("Initializing schema version database...")
    try:
        async with connect_db(cfg, upgrade=True) as db:
            if db.upgraded_from is not Layout.CURRENT:
                log.info(f"Copied {db.upgraded_from} schema versions, previous table kept as {LEGACY_TABLE}")
            latest = await db.find_latest_schema()
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    if latest:
        log.info(f"Schema version database already exists with latest version V{latest.version}")
    else:
        log.info("Schema version database initialized")
    return 0


async def print_tables_sql(cfg: ContextConfig) -> int:
    try:
        sql = create_tables_sql(cfg.schema_db, cfg.schema_db_schema)
    except InvalidDBConnectionError as err:
        return fail(err, Errors.ERR_DB_CONNECTION_FAILED)
    click.echo(sql)
    return 0
