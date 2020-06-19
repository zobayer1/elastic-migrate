# -*- coding: utf-8 -*-
import click

from esmigrate.utils import title
from esmigrate.contexts.context_config import ContextConfig


@click.group(invoke_without_command=True)
@click.help_option(help='Show help index and exit')
@click.version_option(message='%(prog)s v%(version)s', help='Show the version and exit')
@click.option('-p', '--profile', default='dev', help='Set configuration profile')
@click.pass_context
def main(ctx, profile='dev'):
    if ctx.invoked_subcommand is None:
        click.echo(click.style(title, fg='green'))

    ctx.obj = ContextConfig().load_for(profile)


@main.command(help='Initialize schema versions lookup')
@click.pass_obj
def init(cfg):
    click.echo(f'Active profile: {cfg.profile}')
    return True


@main.command(help='Show configuration')
@click.pass_obj
def config(cfg):
    click.echo(f'Active profile: {cfg.profile}')
    return True


@main.command(help='Upgrade to latest/specified schema version')
@click.pass_obj
def upgrade(cfg):
    click.echo(f'Active profile: {cfg.profile}')
    return True


@main.command(help='Downgrade to specified schema version')
@click.pass_obj
def downgrade(cfg):
    click.echo(f'Active profile: {cfg.profile}')
    return True


@main.command(help='Revert to last successful schema version')
@click.pass_obj
def rollback(cfg):
    click.echo(f'Active profile: {cfg.profile}')
    return True


@main.command(help='Reset schema versions lookup')
@click.pass_obj
def reset(cfg):
    click.echo(f'Active profile: {cfg.profile}')
    return True
