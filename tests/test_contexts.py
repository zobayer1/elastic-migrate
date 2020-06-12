# -*- coding: utf-8 -*-
from esmigrate.contexts.context_config import ContextConfig


def test_context_loads():
    assert ContextConfig()
