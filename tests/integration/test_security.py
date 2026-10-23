import base64
import uuid

import pytest
import trustme

from esmigrate.exceptions import Errors
from tests.integration.conftest import ES_MTLS_URL, ES_PASSWORD, ES_SECURE_URL
from tests.integration.test_migrations import CREATE_INDEX, INDEX_DOCUMENT, doc_count, write_schemas

pytestmark = pytest.mark.parametrize("db_url", ["sqlite"], indirect=True)


@pytest.fixture
def index(secure_es):
    """pytest fixture for a unique index name on the secured clusters"""
    return f"esmigrate-it-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def migration(schema_dir, index):
    """pytest fixture writing a two-step migration against the test index"""
    write_schemas(schema_dir, index, {"V1_0__create.exm": CREATE_INDEX, "V1_1__document.exm": INDEX_DOCUMENT})
    return index


def password_auth(certs, **overrides):
    return {
        "elastic_host": ES_SECURE_URL,
        "elastic_username": "elastic",
        "elastic_password": ES_PASSWORD,
        "elastic_ca_certs": certs["ca"],
        **overrides,
    }


def test_basic_auth_with_ca_bundle(esmigrate, profile, certs, migration, secure_es):
    """Test fails if a migration over HTTPS with basic auth and a CA bundle does not succeed"""
    profile(**password_auth(certs))
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert doc_count(secure_es, migration) == 1


def test_password_from_environment_variable(esmigrate, profile, certs, migration, secure_es, monkeypatch):
    """Test fails if a ${VAR} password reference is not resolved for a real connection"""
    monkeypatch.setenv("ESMIGRATE_IT_PASSWORD", ES_PASSWORD)
    profile(**password_auth(certs, elastic_password="${ESMIGRATE_IT_PASSWORD}"))
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert "esmigrate-secret" not in esmigrate("config").output


def test_api_key(esmigrate, profile, certs, migration, secure_es):
    """Test fails if an API key created through the security API cannot run a migration"""
    response = secure_es.post("/_security/api_key", json={"name": f"esmigrate-it-{migration}"})
    response.raise_for_status()
    profile(elastic_host=ES_SECURE_URL, elastic_api_key=response.json()["encoded"], elastic_ca_certs=certs["ca"])
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert doc_count(secure_es, migration) == 1


def test_wrong_password_is_an_http_error(esmigrate, profile, certs, migration):
    """Test fails if rejected credentials are not reported with the elasticsearch HTTP error code"""
    profile(**password_auth(certs, elastic_password="wrong"))
    result = esmigrate("upgrade")
    assert result.exit_code == Errors.ERR_ES_HTTPERROR, result.output
    assert "401 Unauthorized" in result.output


@pytest.mark.parametrize("trust", ["system", "other-ca"])
def test_untrusted_server_certificate_is_a_tls_error(esmigrate, profile, certs, migration, tmp_path, trust):
    """Test fails if a server certificate from an untrusted CA is accepted or not reported as a TLS error"""
    overrides = {}
    if trust == "other-ca":
        trustme.CA().cert_pem.write_to_path(str(tmp_path / "other-ca.pem"))
        overrides["elastic_ca_certs"] = str(tmp_path / "other-ca.pem")
    settings = password_auth(certs, **overrides)
    if trust == "system":
        del settings["elastic_ca_certs"]
    profile(**settings)
    result = esmigrate("upgrade")
    assert result.exit_code == Errors.ERR_ES_CONNERROR, result.output
    assert "TLS error" in result.output
    assert "certificate verify failed" in result.output


def test_disabled_verification_connects_with_warning(esmigrate, profile, certs, migration, secure_es):
    """Test fails if elastic_verify_certs false does not connect or does not warn"""
    settings = password_auth(certs, elastic_verify_certs=False)
    del settings["elastic_ca_certs"]
    profile(**settings)
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    assert "WARNING: TLS certificate verification is disabled" in result.output
    assert doc_count(secure_es, migration) == 1


def test_mutual_tls_with_client_certificate(esmigrate, profile, certs, migration, secure_es):
    """Test fails if a cluster requiring client certificates rejects a configured client certificate"""
    profile(
        **password_auth(
            certs,
            elastic_host=ES_MTLS_URL,
            elastic_client_cert=certs["client_cert"],
            elastic_client_key=certs["client_key"],
        )
    )
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output


def test_mutual_tls_without_client_certificate_is_rejected(esmigrate, profile, certs, migration):
    """Test fails if a cluster requiring client certificates accepts a connection without one"""
    profile(**password_auth(certs, elastic_host=ES_MTLS_URL))
    result = esmigrate("upgrade")
    assert result.exit_code == Errors.ERR_ES_CONNERROR, result.output
    assert "TLS error" in result.output


def test_audit_log_contains_no_secrets_or_bodies(esmigrate, profile, certs, migration, tmp_path):
    """Test fails if the audit log of an authenticated run contains credentials or request bodies"""
    log_file = tmp_path / "audit.log"
    profile(**password_auth(certs, log_file=str(log_file)))
    result = esmigrate("upgrade")
    assert result.exit_code == 0, result.output
    text = log_file.read_text()
    assert f"PUT /{migration} (" in text
    assert f"PUT /{migration}/_doc/1?refresh=true (" in text
    for secret in (ES_PASSWORD, base64.b64encode(f"elastic:{ES_PASSWORD}".encode()).decode(), "alice", "hello"):
        assert secret not in text
