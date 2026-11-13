import logging
import sys

import click

from esmigrate.cli.common import (
    LOG_FILE_KEY,
    PROFILE_KEY,
    fail,
    help_option,
)
from esmigrate.cli.config import config
from esmigrate.cli.init import init
from esmigrate.cli.reset import reset
from esmigrate.cli.rollback import rollback
from esmigrate.cli.unlock import unlock
from esmigrate.cli.upgrade import upgrade
from esmigrate.commons import (
    DEFAULT_PROFILE,
    appname,
    configure_console,
    configure_file,
    version,
)
from esmigrate.exceptions import (
    Errors,
    InvalidConfigurationError,
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


@click.group(invoke_without_command=True)
@help_option
@click.version_option(message="v%(version)s", package_name=appname, help="Show the version and exit")
@click.option("-p", "--profile", default=DEFAULT_PROFILE, show_default=True, help="Use this configuration profile")
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
    """Run versioned schema migrations against Elasticsearch"""
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


main.add_command(config)
main.add_command(init)
main.add_command(reset)
main.add_command(rollback)
main.add_command(unlock)
main.add_command(upgrade)
