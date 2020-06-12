# -*- coding: utf-8 -*-
import click


@click.command(help='Reset schema versions lookup')
@click.pass_obj
def reset(cfg):
    return True
