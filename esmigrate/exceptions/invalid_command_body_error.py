# -*- coding: utf-8 -*-


class InvalidCommandBodyError(RuntimeError):
    """Raised when command body is not a valid JSON object"""
    pass
