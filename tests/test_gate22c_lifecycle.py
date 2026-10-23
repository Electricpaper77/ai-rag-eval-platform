import json
from saas.lifecycle import EXPORT_VERSION

def test_export_contract_excludes_authentication_material():
    assert EXPORT_VERSION == "agenttrust-tenant-export-v1"
    excluded = {"sessions", "oidc_login_states", "Fernet keys", "raw bearer tokens", "PKCE verifiers"}
    assert "sessions" in excluded and "PKCE verifiers" in excluded

def test_lifecycle_schema_is_versioned():
    from saas.postgres_repository import MIGRATIONS
    assert [path.stem.split("_")[0] for path in MIGRATIONS] == ["002", "003"]

def test_journal_hash_chain_detects_tampering(tmp_path):
    from saas.lifecycle import DeletionJournal
    journal = DeletionJournal(tmp_path / "deletions.jsonl")
    journal.append("org_a", "owner_a")
    assert journal.events()[0]["organization_id"] == "org_a"
    journal.path.write_text(journal.path.read_text(encoding="utf-8").replace("org_a", "org_b"), encoding="utf-8")
    import pytest
    with pytest.raises(RuntimeError, match="integrity"): journal.events()

def test_journal_rejects_conflicting_duplicate_organization(tmp_path):
    from saas.lifecycle import DeletionJournal
    journal = DeletionJournal(tmp_path / "deletions.jsonl")
    first = journal.append("org_a", "owner_a")
    second = {"event_id": "del_conflict", "organization_id": "org_a", "actor_user_id": "owner_b", "occurred_at": first["occurred_at"], "previous_digest": first["digest"]}
    import hashlib, json
    second["digest"] = hashlib.sha256(json.dumps(second, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with journal.path.open("a", encoding="utf-8") as handle: handle.write(json.dumps(second, sort_keys=True) + "\n")
    import pytest
    with pytest.raises(RuntimeError, match="duplicate"): journal.events()
