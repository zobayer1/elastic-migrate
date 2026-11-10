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

from esmigrate.commons import (
    DEFAULT_PROFILE,
    Command,
    Direction,
    Migration,
    MigVersion,
    appname,
    configure_console,
    configure_file,
    query_error_string,
    query_results_string,
    version,
)
from esmigrate.contexts import ContextConfig, mask_db_url
from esmigrate.exceptions import (
    ElasticsearchConnError,
    ElasticsearchHTTPError,
    Errors,
    InvalidCommandBodyError,
    InvalidCommandPathError,
    InvalidCommandScriptError,
    InvalidCommandVerbError,
    InvalidConfigurationError,
    InvalidDBConnectionError,
    InvalidSchemaFileError,
    InvalidSchemaPatternError,
    InvalidSchemaTableError,
    LegacySchemaTableError,
    MigrationLockedError,
    SchemaVersionSqlDbError,
    UserProfileNotFoundError,
    error_list,
)
from esmigrate.internals import (
    LEGACY_TABLE,
    DBManager,
    GlobLoader,
    HTTPHandler,
    Layout,
    ScriptParser,
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

SCRIPT_ERRORS = (
    InvalidCommandScriptError,
    InvalidCommandVerbError,
    InvalidCommandPathError,
    InvalidCommandBodyError,
)


def fail(err: Exception, code: int) -> int:
    log.error(f"{type(err).__name__}: {err}")
    return code


def run(coro: Coroutine[Any, Any, int]) -> NoReturn:
    code = asyncio.run(coro)
    log.debug(f"Finished {click.get_current_context().info_name} with exit code {code}")
    sys.exit(code)


@asynccontextmanager
async def migration_lock(cfg: ContextConfig, db: DBManager) -> AsyncGenerator[None, None]:
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


@main.command(help="Upgrade to latest or specified schema version")
@click.help_option(help="Show help index and exit")
@click.option("-s", "--schema-version", default="latest", help="Target schema version, e.g. '1.2' or 'latest'")
@pass_config
def upgrade(cfg: ContextConfig, schema_version: str = "latest") -> None:
    run(run_upgrade(cfg, schema_version))


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


async def run_upgrade(cfg: ContextConfig, schema_version: str) -> int:
    log.debug(f"Upgrade target: {schema_version}")
    try:
        requested = None if schema_version == "latest" else MigVersion.parse(schema_version)
    except ValueError as err:
        return fail(err, Errors.ERR_INVALID_SCMVER)
    try:
        async with connect_db(cfg) as db, migration_lock(cfg, db):
            return await upgrade_schema(cfg, db, requested)
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    except InvalidConfigurationError as err:
        return fail(err, Errors.ERR_INVALID_CONFIGURATION)


def parse_scripts(direction: Direction, migrations: list[Migration]) -> list[tuple[Migration, list[Command]]]:
    parser = ScriptParser()
    parsed: list[tuple[Migration, list[Command]]] = []
    errors: list[str] = []
    for migration in migrations:
        script = migration.script_for(direction)
        if script is None:
            parsed.append((migration, []))
            continue
        try:
            parsed.append((migration, list(parser.get_commands(script.content))))
        except SCRIPT_ERRORS as err:
            errors.append(f"{script.path}: {err}")
    if errors:
        raise InvalidCommandScriptError(error_list("Invalid migration scripts:", errors))
    return parsed


async def apply_schema(
    db: DBManager, http_handler: HTTPHandler, direction: Direction, entry: Migration, commands: list[Command]
) -> int:
    log.info(f"Processing schema {entry.description}")
    script = entry.script_for(direction)
    if script:
        log.debug(f"Schema {entry.version} {direction}: script={script.path} checksum={script.checksum.hex()}")
    else:
        log.info(f"Schema {entry.version} has no {direction} script, recording it without requests")
    run = await db.start_run(direction, entry)
    tic = time.perf_counter()
    error_code = 0
    undo = False
    query_results: list[str] = []
    for command in commands:
        try:
            response = await http_handler.make_requests(command)
        except ElasticsearchConnError as err:
            undo = err.never_reached and not query_results
            query_results.append(query_error_string(command, err))
            error_code = fail(err, Errors.ERR_ES_CONNERROR)
            break
        except ElasticsearchHTTPError as err:
            query_results.append(query_results_string(command, err.response))
            error_code = fail(err, Errors.ERR_ES_HTTPERROR)
            break
        query_results.append(query_results_string(command, response))
    duration = int((time.perf_counter() - tic) * 1000)
    results = ";".join(query_results)
    if undo:
        await db.undo_run(run, duration, results)
    else:
        await db.finish_run(run, error_code == 0, duration, results)
    log.debug(f"Schema {entry.version} {direction} {'succeeded' if error_code == 0 else 'failed'} in {duration} ms")
    if error_code == 0:
        log.info(f"Schema {entry.description} executed successfully")
    return error_code


async def upgrade_schema(cfg: ContextConfig, db: DBManager, requested: MigVersion | None) -> int:
    latest_db_entry = await db.find_latest_schema()
    if latest_db_entry and not latest_db_entry.success:
        state = "failed" if latest_db_entry.success is False else "was interrupted"
        err = SchemaVersionSqlDbError(
            f"Version {latest_db_entry.version} {state}, see `esmigrate status` and resolve it with `esmigrate force`"
        )
        return fail(err, Errors.ERR_DB_IN_ERROR_STATE)
    latest_db_version = latest_db_entry.version if latest_db_entry else MigVersion(0, 0)
    try:
        schema_entries = GlobLoader(cfg).load_migrations(cfg.schema_path)
    except NotADirectoryError as err:
        return fail(err, Errors.ERR_INVALID_SCHEMA_DIRECTORY)
    except (InvalidSchemaPatternError, InvalidSchemaFileError) as err:
        return fail(err, Errors.ERR_INVALID_SCHEMA_FILE)
    if not schema_entries:
        log.info("No schema file found, nothing to do")
        return 0
    applied = await db.find_applied_versions()
    skipped = [entry for entry in schema_entries if entry.version < latest_db_version and entry.version not in applied]
    if skipped:
        title = f"Migrations below the latest applied version {latest_db_version} are skipped:"
        files = [
            f"{entry.version}: {', '.join(script.path for script in (entry.up, entry.down) if script)}"
            for entry in skipped
        ]
        log.warning(error_list(title, files))
    target = schema_entries[-1].version if requested is None else requested
    pending = [entry for entry in schema_entries if latest_db_version < entry.version <= target]
    if not pending:
        if requested is None:
            log.info(f"Schema database is up to date at version {latest_db_version}, nothing to do")
        else:
            log.info(
                f"No migrations to apply up to version {requested} (database at {latest_db_version}), nothing to do"
            )
        return 0
    try:
        parsed = parse_scripts(Direction.UP, pending)
    except InvalidCommandScriptError as err:
        return fail(err, Errors.ERR_INVALID_SCHEMA_COMMAND)
    async with HTTPHandler(cfg) as http_handler:
        for entry, commands in parsed:
            code = await apply_schema(db, http_handler, Direction.UP, entry, commands)
            if code:
                return code
    log.info(f"Schema database upgraded to {pending[-1].version}")
    return 0


async def run_rollback(cfg: ContextConfig) -> int:
    try:
        async with connect_db(cfg) as db, migration_lock(cfg, db):
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
        async with connect_db(cfg) as db, migration_lock(cfg, db):
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
