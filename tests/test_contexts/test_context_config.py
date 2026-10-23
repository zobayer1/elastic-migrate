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


@pytest.mark.parametrize(
    "host",
    [
        "https://my-domain:8000",
        "http://elasticsearch:9200",
        "http://my_host:9200",
        "https://es-prod.example.com:9200",
        "https://10.0.0.5",
        "http://[::1]:9200",
        "https://proxy.example.com/es",
    ],
)
def test_context_accepts_valid_hosts(fs, host):
    """Test fails if valid http(s) hosts, including single-label names from #109, are rejected"""
    write_profile(fs, schema_dir="s", elastic_host=host)
    assert ContextConfig().load_for("test").es_host == host


@pytest.mark.parametrize(
    ("host", "message"),
    [
        ("localhost:9200", "http or https"),
        ("ftp://es.example.com", "http or https"),
        ("https://", "no host name"),
        ("https://es.example.com:99999", "not a valid URL"),
        ("https://es.example.com:0", "invalid port"),
        ("https://elastic:secret@es.example.com", "must not contain credentials"),
        (9200, "must be a string"),
    ],
)
def test_context_rejects_invalid_hosts(fs, host, message):
    """Test fails if an invalid elastic_host is accepted or silently replaced"""
    write_profile(fs, schema_dir="s", elastic_host=host)
    with pytest.raises(InvalidConfigurationError, match=message):
        ContextConfig().load_for("test")


def test_context_interpolates_environment_variables(fs, monkeypatch):
    """Test fails if ${VAR} references are not resolved in string fields, nested headers and lists"""
    monkeypatch.setenv("ES_HOST", "es.internal")
    monkeypatch.setenv("ES_PASSWORD", "s3cr3t")
    monkeypatch.setenv("TENANT", "gov")
    write_profile(
        fs,
        schema_dir="schemas/${TENANT}",
        elastic_host="https://${ES_HOST}:9200",
        elastic_username="migrator",
        elastic_password="${ES_PASSWORD}",
        elastic_headers={"X-Tenant": "${TENANT}"},
        unused=["${TENANT}", 1],
    )
    context = ContextConfig().load_for("test")
    assert context.es_host == "https://es.internal:9200"
    assert context.es_password == "s3cr3t"
    assert context.schema_dir == "schemas/gov"
    assert context.headers == {"X-Tenant": "gov"}


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"elastic_password": "${MISSING_SECRET}"}, "MISSING_SECRET referenced by elastic_password is not set"),
        ({"elastic_headers": {"X-A": "${MISSING_SECRET}"}}, r"referenced by elastic_headers\.X-A"),
        ({"tags": ["${MISSING_SECRET}"]}, r"referenced by tags\[0\]"),
    ],
)
def test_context_rejects_unset_environment_variables(fs, monkeypatch, fields, message):
    """Test fails if a reference to an unset environment variable silently becomes an empty string"""
    monkeypatch.delenv("MISSING_SECRET", raising=False)
    write_profile(fs, schema_dir="s", **fields)
    with pytest.raises(InvalidConfigurationError, match=message):
        ContextConfig().load_for("test")


def test_context_loads_security_fields(fs):
    """Test fails if auth, CA and client certificate fields are not loaded"""
    for path in ("/certs/ca.pem", "/certs/client.pem", "/certs/client.key"):
        fs.create_file(path)
    write_profile(
        fs,
        schema_dir="s",
        elastic_username="migrator",
        elastic_password="pw",
        elastic_ca_certs="/certs/ca.pem",
        elastic_client_cert="/certs/client.pem",
        elastic_client_key="/certs/client.key",
        elastic_client_key_password="keypw",
    )
    context = ContextConfig().load_for("test")
    assert (context.es_username, context.es_password) == ("migrator", "pw")
    assert context.es_ca_certs == "/certs/ca.pem"
    assert (context.es_client_cert, context.es_client_key) == ("/certs/client.pem", "/certs/client.key")
    assert context.es_client_key_password == "keypw"
    assert context.es_verify_certs is True


def test_context_allows_disabled_certificate_verification(fs):
    """Test fails if elastic_verify_certs false is not accepted"""
    write_profile(fs, schema_dir="s", elastic_verify_certs=False)
    assert ContextConfig().load_for("test").es_verify_certs is False


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"elastic_username": "migrator"}, "must be set together"),
        ({"elastic_password": "pw"}, "must be set together"),
        ({"elastic_username": "u", "elastic_password": "p", "elastic_api_key": "k"}, "not both"),
        ({"elastic_client_key": "/certs/client.key"}, "need elastic_client_cert"),
        ({"elastic_client_key_password": "pw"}, "need elastic_client_cert"),
        ({"elastic_ca_certs": "/certs/missing.pem"}, "file does not exist"),
        ({"elastic_ca_certs": "/certs/client.key", "elastic_verify_certs": False}, "no effect"),
        ({"elastic_verify_certs": "false"}, "must be true or false"),
        ({"elastic_api_key": 123}, "elastic_api_key must be a string"),
        ({"elastic_headers": {"X-A": 1}}, "string values"),
        ({"elastic_headers": ["X-A"]}, "string values"),
    ],
)
def test_context_rejects_invalid_security_settings(fs, fields, message):
    """Test fails if inconsistent or invalid auth and TLS settings are accepted"""
    fs.create_file("/certs/client.key")
    write_profile(fs, schema_dir="s", **fields)
    with pytest.raises(InvalidConfigurationError, match=message):
        ContextConfig().load_for("test")


def test_context_masks_secrets(fs):
    """Test fails if passwords, API keys or Authorization headers are printed by repr"""
    fs.create_file("/certs/client.pem")
    write_profiles(
        fs,
        local_config_file_path,
        {"test": {"schema_dir": "s", "elastic_api_key": "api-key-value", "elastic_headers": {"X-Tenant": "gov"}}},
        {
            "headers": {
                "schema_dir": "s",
                "elastic_client_cert": "/certs/client.pem",
                "elastic_client_key_password": "key-password-value",
                "elastic_headers": {"Authorization": "Basic dXNlcjpwYXNz"},
            }
        },
    )
    texts = repr(ContextConfig().load_for("test")) + repr(ContextConfig().load_for("headers"))
    for secret in ("api-key-value", "key-password-value", "dXNlcjpwYXNz"):
        assert secret not in texts
    assert "elastic_api_key: ****" in texts
    assert "elastic_client_key_password: ****" in texts
    assert '"Authorization": "****"' in texts
    assert '"X-Tenant": "gov"' in texts
    assert "elastic_password: None" in texts


@pytest.mark.parametrize("auth", [{"elastic_api_key": "k"}, {"elastic_username": "u", "elastic_password": "p"}])
def test_context_rejects_authorization_header_with_auth_fields(fs, auth):
    """Test fails if an Authorization header is combined with elastic auth fields"""
    write_profile(fs, schema_dir="s", elastic_headers={"authorization": "Basic x"}, **auth)
    with pytest.raises(InvalidConfigurationError, match="conflicts with elastic auth fields"):
        ContextConfig().load_for("test")


def test_context_ignores_profiles_list_missing(fs):
    """Test fails if a config file without a profiles list breaks loading of other files"""
    fs.create_file(user_config_file_path, contents=json.dumps({"other": 1}))
    write_profile(fs, schema_dir="s")
    assert ContextConfig().load_for("test").schema_dir == "s"
