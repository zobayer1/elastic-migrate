# -*- coding: utf-8 -*-
import click

from esmigrate.contexts import ContextConfig
from esmigrate.commons import title
from esmigrate.exceptions import InvalidDBConnectionError, UserProfileNotFoundError, Errors
from esmigrate.internals import get_db_manager


@click.group(invoke_without_command=True)
@click.help_option(help="Show help index and exit")
@click.version_option(message="v%(version)s", help="Show the version and exit")
@click.option("-p", "--profile", default="test", help="Set configuration profile")
@click.pass_context
def main(ctx, profile: str = "test"):
    if ctx.invoked_subcommand is None:
        click.echo(click.style(title, fg="green"))
        exit(0)
    else:
        click.echo(f"Loading profile: {profile}...")
        try:
            ctx.obj = ContextConfig().load_for(profile)
            click.echo(f"Profile loaded: {profile}")
        except UserProfileNotFoundError as err:
            click.echo(f"UserProfileNotFoundError: {str(err)}")
            exit(Errors.ERR_NO_PROFILE)


@main.command(help="Initialize schema version database")
@click.pass_obj
def init(cfg):
    click.echo("Initializing schema version database...")
    try:
        db_manager = get_db_manager(cfg.schema_db)
        latest = db_manager.find_latest_schema()
        if latest:
            click.echo(f"Schema version database already exists with latest version V{latest.version}")
            exit(0)
        else:
            click.echo("Schema version database initialized")
            exit(0)
    except InvalidDBConnectionError:
        click.echo("Error: Invalid database connection URL")
        exit(Errors.ERR_INVALID_DB)


@main.command(help="Show configuration")
@click.pass_obj
def config(cfg):
    click.echo(f"{repr(cfg)}")
    exit(0)


# @main.command(help="Upgrade to latest/specified schema version")
# @click.pass_obj
# def upgrade(cfg):
#     click.echo(f"Active profile: {cfg.profile}")
#     return True
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
