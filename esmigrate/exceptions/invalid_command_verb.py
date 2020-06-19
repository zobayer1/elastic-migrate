# -*- coding: utf-8 -*-


class InvalidCommandVerb(RuntimeError):
    """Raised when command verb is not one of GET, PUT, POST, DELETE"""
    pass
