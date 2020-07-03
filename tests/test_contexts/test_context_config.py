# -*- coding: utf-8 -*-
import pytest

from esmigrate.commons import local_config_file_path, user_config_file_path
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    InvalidSchemaPatternError,
    ConfigurationFileReadError,
    InvalidElasticHostUrlError,
)


def test_context_fails_with_invalid_schema_pattern_error(monkeypatch):
    monkeypatch.setenv("SCHEMA_PATTERN", "some illegal pattern")
    with pytest.raises(InvalidSchemaPatternError):
        ContextConfig()


def test_context_config_loads_from_envvar_config_path(monkeypatch, fs):
    monkeypatch.setenv("ESMIGRATE_CONFIG", "/tmp/elastic-migrate/config.json")
    fs.create_file("/tmp/elastic-migrate/config.json", contents="""{"profiles":[{"test":{}}]}""")
    context = ContextConfig().load_for("test")
    assert context.profile == "test"


def test_context_config_loads_from_cwd_config_path(fs):
    fs.create_file(local_config_file_path, contents="""{"profiles":[{"test":{}}]}""")
    context = ContextConfig().load_for("test")
    assert context.profile == "test"


def test_context_config_loads_from_user_config_path(fs):
    fs.create_file(user_config_file_path, contents="""{"profiles":[{"test":{}}]}""")
    context = ContextConfig().load_for("test")
    assert context.profile == "test"


def test_context_fails_with_configuration_file_read_error(fs):
    fs.create_file(local_config_file_path, contents="not valid json")
    with pytest.raises(ConfigurationFileReadError):
        ContextConfig().load_for("test")


def test_context_fails_with_invalid_elastic_host_url_error(fs):
    fs.create_file(
        local_config_file_path, contents="""{"profiles":[{"test":{"elastic_host":"invalid_host"}}]}""",
    )
    with pytest.raises(InvalidElasticHostUrlError):
        ContextConfig().load_for("test")
