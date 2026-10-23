import json
from saas.lifecycle import EXPORT_VERSION

def test_export_contract_excludes_authentication_material():
    assert EXPORT_VERSION == "agenttrust-tenant-export-v1"
    excluded = {"sessions", "oidc_login_states", "Fernet keys", "raw bearer tokens", "PKCE verifiers"}
    assert "sessions" in excluded and "PKCE verifiers" in excluded

def test_lifecycle_schema_is_versioned():
    from saas.postgres_repository import MIGRATIONS
    assert [path.stem.split("_")[0] for path in MIGRATIONS] == ["002", "003"]
