# -*- coding: utf-8 -*-
import click
from setuptools_scm import get_version

from esmigrate.header import title
from esmigrate.config import Config


@click.group(invoke_without_command=True)
@click.help_option(help='Show help index and exit')
@click.version_option(message='%(prog)s v%(version)s', help='Show the version and exit')
@click.option('-p', '--profile', default='dev', help='Set configuration profile')
@click.pass_context
def main(ctx, profile='dev'):
    if ctx.invoked_subcommand is None:
        version = get_version(root='..', relative_to=__file__).split('+')[0]
        click.echo(click.style(title.format(version), fg='green'))

    ctx.obj = Config().load_for(profile)


@main.command(help='Initialize schema versions lookup')
@click.pass_obj
def init(cfg):
    pass


@main.command(help='Upgrade to latest/specified schema version')
@click.pass_obj
def upgrade(cfg):
    pass


@main.command(help='Downgrade to specified schema version')
@click.pass_obj
def downgrade(cfg):
    pass


@main.command(help='Reset schema versions lookup')
@click.pass_obj
def reset(cfg):
    pass


@main.command(help='Revert to last successful schema version')
@click.pass_obj
def rollback(cfg):
    pass


@main.command(help='Show configuration')
@click.pass_obj
def config(cfg):
    pass
