# -*- coding: utf-8 -*-
import click


@click.command(help='Initialize schema versions lookup')
@click.pass_obj
def init(cfg):
    return True
