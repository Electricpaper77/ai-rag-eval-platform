import time
from pathlib import Path
import pytest
from saas.backup_catalog import BackupRecord, LocalBackupCatalog, catalog_digest
from saas.key_provider import DisposableKeyProvider, require_distinct_approval_roles
def test_rotation_preserves_historical_decryptability_and_blocks_new_encrypt_after_retirement():
    provider = DisposableKeyProvider({"v1": b"a" * 32, "v2": b"b" * 32}); assert provider.decrypt_key("v1", "backup") == b"a" * 32
    provider.retire("v1"); assert provider.decrypt_key("v1", "backup") == b"a" * 32
    with pytest.raises(RuntimeError): provider.encrypt_key("v1", "backup")
    provider.revoke("v1")
    with pytest.raises(RuntimeError): provider.decrypt_key("v1", "backup")
    assert provider.encrypt_key("v2", "backup") == b"b" * 32
def test_key_purpose_and_unknown_key_fail_closed():
    provider = DisposableKeyProvider({"v1": b"a" * 32})
    with pytest.raises(KeyError): provider.decrypt_key("missing", "backup")
    with pytest.raises(RuntimeError): provider.decrypt_key("v1", "session")
def test_restore_approval_requires_distinct_trusted_roles():
    with pytest.raises(RuntimeError): require_distinct_approval_roles("operator", "operator", approver_role="recovery_approver")
    with pytest.raises(RuntimeError): require_distinct_approval_roles("operator", "approver", approver_role="recovery_operator")
    require_distinct_approval_roles("operator", "approver", approver_role="recovery_approver")
def test_catalog_retention_hold_and_integrity(tmp_path: Path):
    record = BackupRecord("b1", "v2", "digest", time.time(), time.time() + 100, legal_hold=True); catalog = LocalBackupCatalog(tmp_path / "catalog.json"); catalog.put(record); loaded = catalog.get("b1")
    assert not catalog.can_delete(loaded, now=time.time() + 1000); assert len(catalog_digest(loaded)) == 64
    with pytest.raises(RuntimeError): catalog.get("other")
def test_alert_rules_are_sanitized_and_low_cardinality():
    text = Path("observability/gate22f_alerts.yml").read_text(); assert "tenant_id" not in text and "connection_string" not in text

