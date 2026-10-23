import pytest

from saas.deployment import validate_deployment_configuration


def configure(monkeypatch, **values):
    for key in (
        "AGENTTRUST_DEPLOYMENT_POLICY", "AGENTTRUST_MANAGED_DEPLOYMENT",
        "AGENTTRUST_SAAS_RUNTIME_MODE", "AGENTTRUST_POSTGRES_URL",
        "AGENTTRUST_SAAS_DB", "AGENTTRUST_SHARED_SESSION_STORE",
        "AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY",
        "AGENTTRUST_OIDC_ISSUER", "AGENTTRUST_OIDC_CLIENT_ID",
        "AGENTTRUST_OIDC_REDIRECT_URI",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("extra", [
    {"AGENTTRUST_POSTGRES_URL": "postgresql://test", "AGENTTRUST_SHARED_SESSION_STORE": "postgres"},
    {"AGENTTRUST_SAAS_DB": "/tmp/saas.sqlite3", "AGENTTRUST_SHARED_SESSION_STORE": "sqlite"},
    {"AGENTTRUST_POSTGRES_URL": "postgresql://test", "AGENTTRUST_SHARED_SESSION_STORE": "memory"},
])
def test_production_requires_managed_postgres_boundary(monkeypatch, extra):
    configure(monkeypatch, AGENTTRUST_DEPLOYMENT_POLICY="production", **extra)
    with pytest.raises(RuntimeError): validate_deployment_configuration()


def test_production_rejects_local_runtime_and_test_identities(monkeypatch):
    configure(monkeypatch, AGENTTRUST_DEPLOYMENT_POLICY="production", AGENTTRUST_MANAGED_DEPLOYMENT="true",
              AGENTTRUST_POSTGRES_URL="postgresql://test", AGENTTRUST_SHARED_SESSION_STORE="postgres",
              AGENTTRUST_SAAS_RUNTIME_MODE="test", AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY='{"token":{"user_id":"u"}}')
    with pytest.raises(RuntimeError): validate_deployment_configuration()


def test_managed_production_configuration_is_accepted(monkeypatch):
    configure(monkeypatch, AGENTTRUST_DEPLOYMENT_POLICY="production", AGENTTRUST_MANAGED_DEPLOYMENT="true",
              AGENTTRUST_POSTGRES_URL="postgresql://test", AGENTTRUST_SHARED_SESSION_STORE="postgres",
              AGENTTRUST_OIDC_STATE_ENCRYPTION_KEY="P7y3zWsvjYfZQTnBjqmAX8MhuXBOT3_5mBJRKeqQpI8=")
    validate_deployment_configuration()


@pytest.mark.parametrize("key", ["not-base64", "c2hvcnQ=", "", "A" * 44])
def test_production_rejects_missing_malformed_or_wrong_size_fernet_keys(monkeypatch, key):
    configure(monkeypatch, AGENTTRUST_DEPLOYMENT_POLICY="production", AGENTTRUST_MANAGED_DEPLOYMENT="true",
              AGENTTRUST_POSTGRES_URL="postgresql://test", AGENTTRUST_SHARED_SESSION_STORE="postgres",
              AGENTTRUST_OIDC_STATE_ENCRYPTION_KEY=key)
    with pytest.raises(RuntimeError, match="Fernet|required"):
        validate_deployment_configuration()
