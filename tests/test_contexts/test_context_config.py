# -*- coding: utf-8 -*-
import pytest

from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import InvalidSchemaPatternError


def test_context_loads():
    context = ContextConfig()
    assert context.profile == 'dev'
    assert len(str(context)) > 0


def test_context_load_fails_with_bad_envvar(monkeypatch):
    monkeypatch.setenv('SCHEMA_PATTERN', 'some illegal pattern')
    with pytest.raises(InvalidSchemaPatternError):
        ContextConfig()
