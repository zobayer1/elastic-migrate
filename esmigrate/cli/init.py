import logging

import click

from esmigrate.cli.common import DB_ERRORS, connect_db, fail, help_option, pass_config, run
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import Errors, InvalidDBConnectionError
from esmigrate.internals import LEGACY_TABLE, Layout, create_tables_sql

log = logging.getLogger(__name__)


@click.command()
@help_option
@click.option("--print-sql", is_flag=True, help="Print the SQL that creates the schema tables, without connecting")
@pass_config
def init(cfg: ContextConfig, print_sql: bool = False) -> None:
    """Create the schema tables, copying v1 and v2 rows if present"""
    run(print_tables_sql(cfg) if print_sql else run_init(cfg))


async def run_init(cfg: ContextConfig) -> int:
    """Create the schema tables, copying v1 and v2 rows if present"""
    try:
        async with connect_db(cfg, upgrade=True) as db:
            copied = db.upgraded_from is not Layout.CURRENT
            if copied:
                log.info(f"Copied the {db.upgraded_from} schema versions, {LEGACY_TABLE} is kept as the backup")
            latest = await db.find_latest_schema()
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    if latest is None:
        log.info("Schema database initialized")
    elif copied:
        log.info(f"Schema database initialized at version {latest.version}")
    else:
        log.info(f"Schema database already initialized at version {latest.version}")
    return 0


async def print_tables_sql(cfg: ContextConfig) -> int:
    """Print the SQL that creates the schema tables"""
    try:
        sql = create_tables_sql(cfg.schema_db, cfg.schema_db_schema)
    except InvalidDBConnectionError as err:
        return fail(err, Errors.ERR_DB_CONNECTION_FAILED)
    click.echo(sql)
    return 0
