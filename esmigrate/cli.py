# -*- coding: utf-8 -*-
import sys

import click

from esmigrate.commons import title
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    InvalidDBConnectionError,
    UserProfileNotFoundError,
    Errors,
    InvalidSchemaPatternError,
    InvalidSchemaFileError,
)
from esmigrate.internals import get_db_manager, GlobLoader


@click.group(invoke_without_command=True)
@click.help_option(help="Show help index and exit")
@click.version_option(message="v%(version)s", help="Show the version and exit")
@click.option("-p", "--profile", default="test", help="Set configuration profile")
@click.pass_context
def main(ctx, profile: str = "test"):
    if ctx.invoked_subcommand is None:
        click.echo(click.style(title, fg="green"))
    else:
        click.echo(f"Loading profile: {profile}...")
        try:
            ctx.obj = ContextConfig().load_for(profile)
            click.echo(f"Profile loaded: {profile}")
        except UserProfileNotFoundError as err:
            click.echo(f"UserProfileNotFoundError: {str(err)}")
            sys.exit(Errors.ERR_PROFILE_NOT_FOUND)


@main.command(help="Initialize schema version database")
@click.help_option(help="Show help index and exit")
@click.pass_obj
def init(cfg):
    click.echo("Initializing schema version database...")
    try:
        db_manager = get_db_manager(cfg.schema_db)
        latest = db_manager.find_latest_schema()
        if latest:
            click.echo(f"Schema version database already exists with latest version V{latest.version}")
        else:
            click.echo("Schema version database initialized")
    except InvalidDBConnectionError as err:
        click.echo(f"InvalidDBConnectionError: {str(err)}")
        sys.exit(Errors.ERR_INVALID_DB)


@main.command(help="Show configuration")
@click.help_option(help="Show help index and exit")
@click.pass_obj
def config(cfg):
    click.echo(f"{repr(cfg)}")


@main.command(help="Upgrade to latest or specified schema version")
@click.help_option(help="Show help index and exit")
@click.option("-s", "--schema-version", default="latest", help="Target schema version, e.g. '1.2' or 'latest'")
@click.pass_obj
def upgrade(cfg, schema_version="latest"):
    try:
        requested_version = None if schema_version == "latest" else float(schema_version)
    except ValueError:
        click.echo(f"ValueError: Invalid --schema-version value: {schema_version}")
        sys.exit(Errors.ERR_INVALID_SCMVER)
    try:
        db_manager = get_db_manager(cfg.schema_db)
        latest_db_entry = db_manager.find_latest_schema()
        if latest_db_entry and not latest_db_entry.success:
            click.echo(f"Error: Schema database contains an error for version {latest_db_entry.version}")
            sys.exit(Errors.ERR_SCHEMA_DB_ERROR)
        latest_db_version = float(latest_db_entry.version) if latest_db_entry else 0.0
    except InvalidDBConnectionError as err:
        click.echo(f"InvalidDBConnectionError: {str(err)}")
        sys.exit(Errors.ERR_INVALID_DB)
    try:
        glob_loader = GlobLoader(cfg)
        schema_entries = glob_loader.scan_dir(cfg.schema_dir)
        file_count = len(schema_entries)
        if file_count == 0:
            click.echo("No schema file found, Nothing to do")
            return
        latest_file_version = float(f"{schema_entries[-1].version_base}.{schema_entries[-1].version_rank}")
        if not requested_version:
            requested_version = latest_file_version
    except NotADirectoryError as err:
        click.echo(f"NotADirectoryError: {str(err)}")
        sys.exit(Errors.ERR_NOT_A_DIR)
    except (InvalidSchemaPatternError, InvalidSchemaFileError) as err:
        click.echo(f"Error: {str(err)}")
        sys.exit(Errors.ERR_SCHEMA_FILE_ERROR)

    click.echo(f"Requested version for upgrade: {requested_version}")
    click.echo(f"Latest version in schema directory: {latest_file_version}")
    click.echo(f"Latest version in schema database: {latest_db_version}")


#
#
# @main.command(help="Downgrade to specified schema version")
# @click.pass_obj
# def downgrade(cfg):
#     click.echo(f"Active profile: {cfg.profile}")
#     return True
#
#
# @main.command(help="Revert to last successful schema version")
# @click.pass_obj
# def rollback(cfg):
#     click.echo(f"Active profile: {cfg.profile}")
#     return True
#
#
# @main.command(help="Reset schema versions lookup")
# @click.pass_obj
# def reset(cfg):
#     click.echo(f"Active profile: {cfg.profile}")
#     return True
