# -*- coding: utf-8 -*-
import click

from esmigrate.apis import init_cmd, config_cmd, upgrade_cmd, downgrade_cmd, rollback_cmd, reset_cmd
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


main.add_command(init_cmd)
main.add_command(config_cmd)
main.add_command(upgrade_cmd)
main.add_command(downgrade_cmd)
main.add_command(rollback_cmd)
main.add_command(reset_cmd)
