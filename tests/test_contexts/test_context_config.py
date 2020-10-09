# -*- coding: utf-8 -*-
import pytest

from esmigrate.commons import local_config_file_path, user_config_file_path
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    InvalidSchemaPatternError,
    UserProfileNotFoundError,
)


def test_context_fails_with_invalid_schema_pattern_error(monkeypatch):
    """Test fails if ContextConfig can be instantiated with invalid pattern set via env variable"""
    monkeypatch.setenv("SCHEMA_PATTERN", "some illegal pattern")
    with pytest.raises(InvalidSchemaPatternError):
        ContextConfig()


def test_context_fails_with_user_profile_not_found_error():
    """Test fails if requested profile is not available in any configuration file"""
    with pytest.raises(UserProfileNotFoundError):
        ContextConfig().load_for("some-profile")


def test_context_silently_skips_invalid_json_in_load_order(monkeypatch, fs):
    """Test fails if context loader cannot load configuration files silently in order"""
    monkeypatch.setenv("ESMIGRATE_CONFIG", "/tmp/elastic-migrate/config.json")
    fs.create_file("/tmp/elastic-migrate/config.json", contents="""not a json""")
    fs.create_file(
        user_config_file_path,
        contents="""{"profiles":[{"test":{"schema_ext": ".exm1", "schema_dir": "dir1"}}]}""",
    )
    fs.create_file(
        local_config_file_path,
        contents="""{"profiles":[{"test":{"schema_ext": ".exm2", "elastic_host": "http://127.0.0.1:9200"}}]}""",
    )
    context = ContextConfig().load_for("test")
    assert context.profile == "test"
    assert context.schema_dir == "dir1"
    assert context.schema_ext == ".exm2"
    assert context.es_host == "http://127.0.0.1:9200"
