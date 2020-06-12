# -*- coding: utf-8 -*-
import click


@click.command(help='Upgrade to latest/specified schema version')
@click.pass_obj
def upgrade(cfg):
    return True
