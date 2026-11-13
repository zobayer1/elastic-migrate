import logging
import sys

import click

from esmigrate.cli.common import (
    DB_ERRORS,
    LOG_FILE_KEY,
    PROFILE_KEY,
    connect_db,
    fail,
    hold_lock,
    pass_config,
    run,
)
from esmigrate.cli.upgrade import upgrade
from esmigrate.commons import (
    DEFAULT_PROFILE,
    appname,
    configure_console,
    configure_file,
    version,
)
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    Errors,
    InvalidConfigurationError,
    InvalidDBConnectionError,
)
from esmigrate.internals import (
    LEGACY_TABLE,
    Layout,
    create_tables_sql,
)

title = f"""
  ███████╗███████╗    ███╗   ███╗██╗ ██████╗ ██████╗  █████╗ ████████╗███████╗
  ██╔════╝██╔════╝    ████╗ ████║██║██╔════╝ ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝
  █████╗  ███████╗    ██╔████╔██║██║██║  ███╗██████╔╝███████║   ██║   █████╗
  ██╔══╝  ╚════██║    ██║╚██╔╝██║██║██║   ██║██╔══██╗██╔══██║   ██║   ██╔══╝
  ███████╗███████║    ██║ ╚═╝ ██║██║╚██████╔╝██║  ██║██║  ██║   ██║   ███████╗
  ╚══════╝╚══════╝    ╚═╝     ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚══════╝  {version}
  Elasticsearch migrations made easy!
"""

log = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.help_option(help="Show help index and exit")
@click.version_option(message="v%(version)s", package_name=appname, help="Show the version and exit")
@click.option("-p", "--profile", default=DEFAULT_PROFILE, show_default=True, help="Set configuration profile")
@click.option("-v", "--verbose", is_flag=True, help="Show debug output, including every request")
@click.option("-q", "--quiet", is_flag=True, help="Show warnings and errors only")
@click.option(
    "--log-file", type=click.Path(dir_okay=False), help="Write a debug log file, overriding the profile log_file"
)
@click.pass_context
def main(
    ctx: click.Context,
    profile: str = DEFAULT_PROFILE,
    verbose: bool = False,
    quiet: bool = False,
    log_file: str | None = None,
) -> None:
    if verbose and quiet:
        raise click.UsageError("--verbose and --quiet cannot be used together")
    configure_console(logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO)
    try:
        configure_file(log_file)
    except InvalidConfigurationError as err:
        sys.exit(fail(err, Errors.ERR_INVALID_CONFIGURATION))
    ctx.meta[PROFILE_KEY] = profile
    ctx.meta[LOG_FILE_KEY] = log_file
    if ctx.invoked_subcommand is None:
        click.echo(click.style(title, fg="green"))


main.add_command(upgrade)


@main.command(help="Create the schema tables, copying rows from v1 and v2 tables if present")
@click.help_option(help="Show help index and exit")
@click.option("--print-sql", is_flag=True, help="Print the SQL that creates the schema tables, without connecting")
@pass_config
def init(cfg: ContextConfig, print_sql: bool = False) -> None:
    run(print_tables_sql(cfg) if print_sql else run_init(cfg))


@main.command(help="Show configuration")
@click.help_option(help="Show help index and exit")
@pass_config
def config(cfg: ContextConfig) -> None:
    click.echo(f"{cfg!r}")


@main.command(help="Revert to last successful schema version")
@click.help_option(help="Show help index and exit")
@pass_config
def rollback(cfg: ContextConfig) -> None:
    run(run_rollback(cfg))


@main.command(help="Reset schema versions lookup")
@click.help_option(help="Show help index and exit")
@pass_config
def reset(cfg: ContextConfig) -> None:
    run(run_reset(cfg))


@main.command(help="Remove a stuck SQLite migration lock left by a crashed run")
@click.help_option(help="Show help index and exit")
@click.option("-y", "--yes", is_flag=True, help="Do not ask for confirmation")
@pass_config
def unlock(cfg: ContextConfig, yes: bool = False) -> None:
    if not yes and not click.confirm(f"Remove the migration lock for namespace {cfg.schema_namespace}?"):
        log.info("Unlock cancelled")
        sys.exit(0)
    run(run_unlock(cfg))


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


async def run_rollback(cfg: ContextConfig) -> int:
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


async def run_reset(cfg: ContextConfig) -> int:
    try:
        async with connect_db(cfg) as db, hold_lock(cfg, db):
            await db.delete_all_schema()
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    log.info("Schema database successfully reset")
    return 0


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
