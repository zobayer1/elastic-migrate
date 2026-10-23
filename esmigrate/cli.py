import asyncio
import sys
import time
from collections.abc import Coroutine
from contextlib import AbstractAsyncContextManager
from typing import Any, NoReturn

import click

from esmigrate.commons import ScriptData, appname, parse_version, query_results_string, title
from esmigrate.contexts import ContextConfig
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
    LegacySchemaTableError,
    SchemaVersionSqlDbError,
    UserProfileNotFoundError,
)
from esmigrate.internals import DBManager, GlobLoader, HTTPHandler, ScriptParser
from esmigrate.internals.db_manager import LEGACY_BACKUP_TABLE
from esmigrate.models import SchemaVersion

DB_ERRORS = {
    InvalidDBConnectionError: Errors.ERR_DB_CONNECTION_FAILED,
    LegacySchemaTableError: Errors.ERR_DB_LEGACY_TABLE,
    SchemaVersionSqlDbError: Errors.ERR_DB_IN_ERROR_STATE,
}

SCRIPT_ERRORS = (
    InvalidCommandScriptError,
    InvalidCommandVerbError,
    InvalidCommandPathError,
    InvalidCommandBodyError,
)


def fail(err: Exception, code: int) -> int:
    click.echo(f"{type(err).__name__}: {err}")
    return code


def run(coro: Coroutine[Any, Any, int]) -> NoReturn:
    sys.exit(asyncio.run(coro))


def connect_db(cfg: ContextConfig, upgrade: bool = False) -> AbstractAsyncContextManager[DBManager]:
    return DBManager.connect(cfg.schema_db, namespace=cfg.schema_namespace, upgrade=upgrade)


@click.group(invoke_without_command=True)
@click.help_option(help="Show help index and exit")
@click.version_option(message="v%(version)s", package_name=appname, help="Show the version and exit")
@click.option("-p", "--profile", default="test", help="Set configuration profile")
@click.pass_context
def main(ctx: click.Context, profile: str = "test") -> None:
    if ctx.invoked_subcommand is None:
        click.echo(click.style(title, fg="green"))
        return
    click.echo(f"Loading profile: {profile}...")
    try:
        ctx.obj = ContextConfig().load_for(profile)
    except UserProfileNotFoundError as err:
        sys.exit(fail(err, Errors.ERR_PROFILE_NOT_FOUND))
    except InvalidConfigurationError as err:
        sys.exit(fail(err, Errors.ERR_INVALID_CONFIGURATION))
    click.echo(f"Profile loaded: {profile}")
    if not ctx.obj.es_verify_certs:
        click.echo(
            "WARNING: TLS certificate verification is disabled (elastic_verify_certs: false), "
            "connections to Elasticsearch are not authenticated",
            err=True,
        )


@main.command(help="Initialize schema version database, upgrading a v1 table if present")
@click.help_option(help="Show help index and exit")
@click.pass_obj
def init(cfg: ContextConfig) -> None:
    run(run_init(cfg))


@main.command(help="Show configuration")
@click.help_option(help="Show help index and exit")
@click.pass_obj
def config(cfg: ContextConfig) -> None:
    click.echo(f"{cfg!r}")


@main.command(help="Upgrade to latest or specified schema version")
@click.help_option(help="Show help index and exit")
@click.option("-s", "--schema-version", default="latest", help="Target schema version, e.g. '1.2' or 'latest'")
@click.pass_obj
def upgrade(cfg: ContextConfig, schema_version: str = "latest") -> None:
    run(run_upgrade(cfg, schema_version))


@main.command(help="Revert to last successful schema version")
@click.help_option(help="Show help index and exit")
@click.pass_obj
def rollback(cfg: ContextConfig) -> None:
    run(run_rollback(cfg))


@main.command(help="Reset schema versions lookup")
@click.help_option(help="Show help index and exit")
@click.pass_obj
def reset(cfg: ContextConfig) -> None:
    run(run_reset(cfg))


async def run_init(cfg: ContextConfig) -> int:
    click.echo("Initializing schema version database...")
    try:
        async with connect_db(cfg, upgrade=True) as db:
            if db.upgraded_legacy_table:
                click.echo(f"Upgraded v1 schema version table, previous table kept as {LEGACY_BACKUP_TABLE}")
            latest = await db.find_latest_schema()
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    if latest:
        click.echo(f"Schema version database already exists with latest version V{latest.version}")
    else:
        click.echo("Schema version database initialized")
    return 0


async def run_upgrade(cfg: ContextConfig, schema_version: str) -> int:
    try:
        requested = None if schema_version == "latest" else parse_version(schema_version)
    except ValueError as err:
        return fail(err, Errors.ERR_INVALID_SCMVER)
    try:
        async with connect_db(cfg) as db:
            return await upgrade_schema(cfg, db, requested)
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    except InvalidConfigurationError as err:
        return fail(err, Errors.ERR_INVALID_CONFIGURATION)


async def upgrade_schema(cfg: ContextConfig, db: DBManager, requested: tuple[int, int] | None) -> int:
    latest_db_entry = await db.find_latest_schema()
    if latest_db_entry and not latest_db_entry.success:
        click.echo(f"Error: Schema database contains an error for version {latest_db_entry.version}")
        return Errors.ERR_DB_IN_ERROR_STATE
    latest_db_version = parse_version(latest_db_entry.version) if latest_db_entry else (0, 0)
    try:
        schema_entries = GlobLoader(cfg).scan_dir(cfg.schema_path)
    except NotADirectoryError as err:
        return fail(err, Errors.ERR_INVALID_SCHEMA_DIRECTORY)
    except (InvalidSchemaPatternError, InvalidSchemaFileError) as err:
        return fail(err, Errors.ERR_INVALID_SCHEMA_FILE)
    if not schema_entries:
        click.echo("No schema file found, nothing to do")
        return 0
    target = schema_entries[-1].version_key if requested is None else requested
    pending = [entry for entry in schema_entries if latest_db_version < entry.version_key <= target]
    if not pending:
        click.echo("Schema version in database is ahead of requested version, nothing to do")
        return 0
    script_parser = ScriptParser()
    async with HTTPHandler(cfg) as http_handler:
        for entry in pending:
            code = await apply_schema(db, http_handler, script_parser, entry)
            if code:
                return code
    click.echo(f"Schema database upgraded to {pending[-1].version}")
    return 0


async def apply_schema(db: DBManager, http_handler: HTTPHandler, script_parser: ScriptParser, entry: ScriptData) -> int:
    click.echo(f"Processing schema {entry.description}")
    query_results = []
    error_code = 0
    tic = time.perf_counter()
    try:
        commands = list(script_parser.get_commands(entry.content))
    except SCRIPT_ERRORS as err:
        commands = []
        error_code = fail(err, Errors.ERR_INVALID_SCHEMA_COMMAND)
    for command in commands:
        try:
            response = await http_handler.make_requests(command)
        except ElasticsearchConnError as err:
            return fail(err, Errors.ERR_ES_CONNERROR)
        except ElasticsearchHTTPError as err:
            query_results.append(query_results_string(command, err.response))
            error_code = fail(err, Errors.ERR_ES_HTTPERROR)
            break
        query_results.append(query_results_string(command, response))
    scmver = SchemaVersion.from_script_data(entry)
    scmver.success = error_code == 0
    scmver.execution_time = int(time.perf_counter() - tic)
    scmver.query_results = ";".join(query_results)
    await db.insert_new_schema(scmver)
    if error_code == 0:
        click.echo(f"Schema {entry.description} executed successfully")
    return error_code


async def run_rollback(cfg: ContextConfig) -> int:
    try:
        async with connect_db(cfg) as db:
            latest = await db.find_latest_schema()
            if latest and not latest.success:
                click.echo(f"Schema database has error entry for version {latest.version}")
                await db.delete_all_failed_schema()
                click.echo("Rollback successful")
            else:
                click.echo("Schema database does not have any error entry")
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    return 0


async def run_reset(cfg: ContextConfig) -> int:
    try:
        async with connect_db(cfg) as db:
            await db.delete_all_schema()
    except tuple(DB_ERRORS) as err:
        return fail(err, DB_ERRORS[type(err)])
    click.echo("Schema database successfully reset")
    return 0
