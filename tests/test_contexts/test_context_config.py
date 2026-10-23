import json

import pytest

from esmigrate.commons import local_config_file_path, user_config_file_path
from esmigrate.contexts import ContextConfig
from esmigrate.exceptions import (
    InvalidConfigurationError,
    InvalidSchemaPatternError,
    UserProfileNotFoundError,
)


def write_profiles(fs, path, *profiles):
    fs.create_file(path, contents=json.dumps({"profiles": list(profiles)}))


def write_profile(fs, **fields):
    write_profiles(fs, local_config_file_path, {"test": fields})


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
    write_profiles(fs, user_config_file_path, {"test": {"schema_ext": ".exm1", "schema_dir": "dir1"}})
    write_profiles(
        fs, local_config_file_path, {"test": {"schema_ext": ".exm2", "elastic_host": "http://127.0.0.1:9200"}}
    )
    context = ContextConfig().load_for("test")
    assert context.profile == "test"
    assert context.schema_dir == "dir1"
    assert context.schema_ext == ".exm2"
    assert context.es_host == "http://127.0.0.1:9200"


def test_context_defaults_schema_namespace():
    """Test fails if a new context does not use the default schema namespace"""
    context = ContextConfig()
    assert context.schema_namespace == "default"
    assert "schema_namespace: default" in repr(context)


def test_context_loads_schema_namespace(fs):
    """Test fails if schema_namespace is not read from the profile"""
    write_profile(fs, schema_dir="s", schema_namespace="billing")
    assert ContextConfig().load_for("test").schema_namespace == "billing"


def test_context_defaults_elastic_timeout():
    """Test fails if the default elasticsearch timeout is not 60 seconds"""
    context = ContextConfig()
    assert context.es_timeout == 60.0
    assert "elastic_timeout: 60.0" in repr(context)


@pytest.mark.parametrize(("value", "expected"), [(5, 5.0), (2.5, 2.5), (None, None)])
def test_context_loads_elastic_timeout(fs, value, expected):
    """Test fails if elastic_timeout is not read as seconds, with null disabling the timeout"""
    write_profile(fs, schema_dir="s", elastic_timeout=value)
    assert ContextConfig().load_for("test").es_timeout == expected


@pytest.mark.parametrize("value", [0, -1, "60", True])
def test_context_rejects_invalid_elastic_timeout(fs, value):
    """Test fails if a non-positive or non-numeric elastic_timeout is accepted"""
    write_profile(fs, schema_dir="s", elastic_timeout=value)
    with pytest.raises(InvalidConfigurationError, match="elastic_timeout"):
        ContextConfig().load_for("test")


def test_context_finds_profile_among_other_profiles(fs):
    """Test fails if the loader does not skip other profiles and files without the requested profile"""
    write_profiles(fs, user_config_file_path, {"other": {"schema_ext": ".nope"}})
    write_profiles(
        fs,
        local_config_file_path,
        {"other": {"schema_ext": ".nope"}},
        {"test": {"schema_dir": "s", "schema_ext": ".yes"}},
    )
    assert ContextConfig().load_for("test").schema_ext == ".yes"


@pytest.mark.parametrize("profile_data", [{}, {"schema_dir": ""}, {"schema_dir": None}])
def test_context_requires_schema_dir(fs, profile_data):
    """Test fails if a profile without a schema_dir is accepted"""
    write_profile(fs, **profile_data)
    with pytest.raises(InvalidConfigurationError, match="schema_dir is required in profile 'test'"):
        ContextConfig().load_for("test")


def test_context_schema_path_requires_schema_dir():
    """Test fails if schema_path silently falls back when schema_dir is unset"""
    with pytest.raises(InvalidConfigurationError, match="schema_dir is not configured"):
        _ = ContextConfig().schema_path
