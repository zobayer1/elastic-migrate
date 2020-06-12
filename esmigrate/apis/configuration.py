# -*- coding: utf-8 -*-
import click


@click.command(help='Show configuration')
@click.pass_obj
def config(cfg):
    return True
