# -*- coding: utf-8 -*-
import click


@click.command(help='Revert to last successful schema version')
@click.pass_obj
def rollback(cfg):
    return True
