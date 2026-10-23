import sys
import time

import click
from requests.exceptions import HTTPError

from esmigrate.commons import appname, parse_version, query_results_string, title
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    ElasticsearchConnError,
    Errors,
    InvalidCommandBodyError,
    InvalidCommandPathError,
    InvalidCommandScriptError,
    InvalidCommandVerbError,
    InvalidDBConnectionError,
    InvalidSchemaFileError,
    InvalidSchemaPatternError,
    SchemaVersionSqlDbError,
    UserProfileNotFoundError,
)
from esmigrate.internals import GlobLoader, HTTPHandler, ScriptParser, get_db_manager
from esmigrate.models import SchemaVersion


@click.group(invoke_without_command=True)
@click.help_option(help="Show help index and exit")
@click.version_option(message="v%(version)s", package_name=appname, help="Show the version and exit")
@click.option("-p", "--profile", default="test", help="Set configuration profile")
@click.pass_context
def main(ctx: click.Context, profile: str = "test") -> None:
    if ctx.invoked_subcommand is None:
        click.echo(click.style(title, fg="green"))
    else:
        click.echo(f"Loading profile: {profile}...")
        try:
            ctx.obj = ContextConfig().load_for(profile)
            click.echo(f"Profile loaded: {profile}")
        except UserProfileNotFoundError as err:
            click.echo(f"UserProfileNotFoundError: {err!s}")
            sys.exit(Errors.ERR_PROFILE_NOT_FOUND)


@main.command(help="Initialize schema version database")
@click.help_option(help="Show help index and exit")
@click.pass_obj
def init(cfg: ContextConfig) -> None:
    click.echo("Initializing schema version database...")
    try:
        db_manager = get_db_manager(cfg.schema_db)
        latest = db_manager.find_latest_schema()
        if latest:
            click.echo(f"Schema version database already exists with latest version V{latest.version}")
        else:
            click.echo("Schema version database initialized")
    except InvalidDBConnectionError as err:
        click.echo(f"InvalidDBConnectionError: {err!s}")
        sys.exit(Errors.ERR_DB_CONNECTION_FAILED)


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
    try:
        requested_version = None if schema_version == "latest" else parse_version(schema_version)
    except ValueError:
        click.echo(f"ValueError: Invalid schema-version value: {schema_version}")
        sys.exit(Errors.ERR_INVALID_SCMVER)
    try:
        db_manager = get_db_manager(cfg.schema_db)
        latest_db_entry = db_manager.find_latest_schema()
        if latest_db_entry and not latest_db_entry.success:
            click.echo(f"Error: Schema database contains an error for version {latest_db_entry.version}")
            sys.exit(Errors.ERR_DB_IN_ERROR_STATE)
        latest_db_version = parse_version(latest_db_entry.version) if latest_db_entry else (0, 0)
    except InvalidDBConnectionError as err:
        click.echo(f"InvalidDBConnectionError: {err!s}")
        sys.exit(Errors.ERR_DB_CONNECTION_FAILED)
    try:
        glob_loader = GlobLoader(cfg)
        schema_entries = glob_loader.scan_dir(cfg.schema_dir)
        file_count = len(schema_entries)
        if file_count == 0:
            click.echo("No schema file found, nothing to do")
            sys.exit(0)
        latest_file_version = schema_entries[-1].version_key
        if requested_version is None:
            requested_version = latest_file_version
    except NotADirectoryError as err:
        click.echo(f"NotADirectoryError: {err!s}")
        sys.exit(Errors.ERR_INVALID_SCHEMA_DIRECTORY)
    except (InvalidSchemaPatternError, InvalidSchemaFileError) as err:
        click.echo(f"Error: {err!s}")
        sys.exit(Errors.ERR_INVALID_SCHEMA_FILE)
    if requested_version <= latest_db_version or latest_file_version <= latest_db_version:
        click.echo("Schema version in database is ahead of requested version, nothing to do")
        sys.exit(0)
    script_parser = ScriptParser(cfg)
    http_handler = HTTPHandler(cfg)
    installed_rank = latest_db_entry.installed_rank if latest_db_entry else 0
    latest = latest_db_entry.version if latest_db_entry else "0.0"
    for scm_entry in filter(
        lambda entry: latest_db_version < entry.version_key <= requested_version,
        schema_entries,
    ):
        click.echo(f"Processing schema {scm_entry.description}")
        commands = []
        query_results = []
        installed_rank += 1
        error_state = None
        tic = time.perf_counter()
        try:
            commands = list(script_parser.get_commands(scm_entry.content))
        except (
            InvalidCommandScriptError,
            InvalidCommandVerbError,
            InvalidCommandPathError,
            InvalidCommandBodyError,
        ) as err:
            error_state = (Errors.ERR_INVALID_SCHEMA_COMMAND, err)
            click.echo(f"Error: {err!s}")
        for command in commands:
            try:
                response = http_handler.make_requests(command)
                query_results.append(query_results_string(command, response))
            except ElasticsearchConnError as err:
                click.echo(f"ElasticsearchConnError: {err!s}")
                sys.exit(Errors.ERR_ES_CONNERROR)
            except HTTPError as err:
                query_results.append(query_results_string(command, err.response))
                error_state = (Errors.ERR_ES_HTTPERROR, err)
                click.echo(f"ElasticsearchHTTPError: {err!s}")
                break
        toc = time.perf_counter()
        scmver = SchemaVersion.from_script_data(scm_entry)
        scmver.installed_rank = installed_rank
        scmver.success = error_state is None
        scmver.execution_time = int(toc - tic)
        scmver.query_results = ";".join(query_results)
        try:
            db_manager.insert_new_schema(scmver)
            latest = scmver.version
        except SchemaVersionSqlDbError as err:
            click.echo(f"SchemaVersionSqlDbError: {err!s}")
            sys.exit(Errors.ERR_DB_IN_ERROR_STATE)
        if error_state:
            click.echo(f"Error occurred: {error_state}")
            sys.exit(error_state[0])
        else:
            click.echo(f"Schema {scm_entry.description} executed successfully")
    click.echo(f"Schema database upgraded to {latest}")


@main.command(help="Revert to last successful schema version")
@click.pass_obj
def rollback(cfg: ContextConfig) -> None:
    try:
        db_manager = get_db_manager(cfg.schema_db)
        latest_db_entry = db_manager.find_latest_schema()
        if latest_db_entry and not latest_db_entry.success:
            click.echo(f"Schema database has error entry for version {latest_db_entry.version}")
            db_manager.delete_all_failed_schema()
            click.echo("Rollback successful")
        else:
            click.echo("Schema database does not have any error entry")
    except SchemaVersionSqlDbError as err:
        click.echo(f"SchemaVersionSqlDbError: {err!s}")
        sys.exit(Errors.ERR_DB_IN_ERROR_STATE)
    except InvalidDBConnectionError as err:
        click.echo(f"InvalidDBConnectionError: {err!s}")
        sys.exit(Errors.ERR_DB_CONNECTION_FAILED)


@main.command(help="Reset schema versions lookup")
@click.pass_obj
def reset(cfg: ContextConfig) -> None:
    try:
        db_manager = get_db_manager(cfg.schema_db)
        db_manager.delete_all_schema()
        click.echo("Schema database successfully reset")
    except SchemaVersionSqlDbError as err:
        click.echo(f"SchemaVersionSqlDbError: {err!s}")
        sys.exit(Errors.ERR_DB_IN_ERROR_STATE)
    except InvalidDBConnectionError as err:
        click.echo(f"InvalidDBConnectionError: {err!s}")
        sys.exit(Errors.ERR_DB_CONNECTION_FAILED)
