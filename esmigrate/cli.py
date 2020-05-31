import click
from setuptools_scm import get_version


@click.group()
@click.help_option(help='Show help index and exit')
@click.version_option(message='%(prog)s %(version)s', help='Show the version and exit')
@click.option('-p', '--profile', default='dev', help='Set configuration profile')
@click.pass_context
def main(ctx, profile='dev'):
    version = get_version(root='..', relative_to=__file__).split('+')[0]
    click.echo(f"""
        ███████╗███████╗    ███╗   ███╗██╗ ██████╗ ██████╗  █████╗ ████████╗███████╗
        ██╔════╝██╔════╝    ████╗ ████║██║██╔════╝ ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝
        █████╗  ███████╗    ██╔████╔██║██║██║  ███╗██████╔╝███████║   ██║   █████╗
        ██╔══╝  ╚════██║    ██║╚██╔╝██║██║██║   ██║██╔══██╗██╔══██║   ██║   ██╔══╝
        ███████╗███████║    ██║ ╚═╝ ██║██║╚██████╔╝██║  ██║██║  ██║   ██║   ███████╗
        ╚══════╝╚══════╝    ╚═╝     ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚══════╝ {version}""")


@main.command(help='Initialize schema versions lookup')
@click.pass_obj
def init():
    pass


@main.command(help='Upgrade to latest/specified schema version')
@click.pass_obj
def upgrade():
    pass


@main.command(help='Downgrade to specified schema version')
@click.pass_obj
def downgrade():
    pass


@main.command(help='Reset schema versions lookup')
@click.pass_obj
def reset():
    pass


@main.command(help='Roll back to last successful schema version')
@click.pass_obj
def rollback():
    pass


@main.command(help='Show configuration')
@click.pass_obj
def config():
    pass
