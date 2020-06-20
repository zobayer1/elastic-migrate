# -*- coding: utf-8 -*-
from esmigrate.contexts import ContextConfig


def test_context_loads():
    context = ContextConfig()
    assert context.profile == 'dev'
