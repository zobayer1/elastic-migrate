import click

from esmigrate.cli.common import pass_config
from esmigrate.contexts import ContextConfig


@click.command(help="Show configuration")
@click.help_option(help="Show help index and exit")
@pass_config
def config(cfg: ContextConfig) -> None:
    click.echo(f"{cfg!r}")
