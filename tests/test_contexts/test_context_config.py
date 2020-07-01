# -*- coding: utf-8 -*-
import os
import re

import pytest

from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import InvalidSchemaPatternError


@pytest.fixture(scope="function")
def parameter(request):
    return request.param


def test_context_loads_with_defaults():
    context = ContextConfig()
    assert context.profile == "dev"
    assert len(str(context)) > 0


def test_context_fails_with_invalid_schema_pattern_error(monkeypatch):
    monkeypatch.setenv("SCHEMA_PATTERN", "some illegal pattern")
    with pytest.raises(InvalidSchemaPatternError):
        ContextConfig()


@pytest.mark.parametrize(
    "parameter",
    [
        "V1_1__create_index_mapping_for_twitter.exm",
        "V1_2__create_new_doc_in_twitter.exm",
        "V1_3__update_existing_doc_in_twitter.exm",
        "V1_3__update_existing_doc_in_twitter.exm",
        "V1_4__delete_all_doc_in_twitter.exm",
        "V1_5__delete_index_twitter.exm",
    ],
    indirect=["parameter"],
)
def test_envvar_regex(monkeypatch, parameter):
    monkeypatch.setenv(
        "SCHEMA_PATTERN",
        "V(?P<version>[\\d]+)_(?P<sequence>[\\d]+)__(?P<name>[\\w]+)\\.(?P<extension>[\\w]+)",
    )

    _context = ContextConfig()
    _pattern = rf"^{os.getenv('SCHEMA_PATTERN')}$"
    assert _context.schema_pattern == _pattern

    assert re.match(_pattern, parameter)
