# -*- coding: utf-8 -*-
import click


@click.command(help='Downgrade to specified schema version')
@click.pass_obj
def downgrade(cfg):
    return True
