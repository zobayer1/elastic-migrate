import click

from esmigrate.cli.common import help_option, pass_config
from esmigrate.contexts import ContextConfig


@click.command()
@help_option
@pass_config
def config(cfg: ContextConfig) -> None:
    """Show the loaded profile, with secrets masked"""
    click.echo(f"{cfg!r}")
