import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
import pytest
from saas.recovery import write_approval, validate_approval, require_recovery_ready

def test_restore_approval_is_bound_expiring_and_fail_closed(tmp_path):
    os.environ["AGENTTRUST_RECOVERY_APPROVAL_KEY"] = "x" * 32; os.environ["AGENTTRUST_RECOVERY_APPROVERS"] = "operator"
    path = tmp_path / "approval.json"; payload = write_approval(path, "backup-a", "journal-a", "operator", ttl_seconds=30, target_database="restore_db")
    assert validate_approval(path, "backup-a", "journal-a", now_epoch=payload["expires_at"] - 1, target_database="restore_db")["operation_id"] == payload["operation_id"]
    with pytest.raises(RuntimeError, match="digest"): validate_approval(path, "backup-b", "journal-a")
    record = json.loads(path.read_text()); record["payload"]["approved_by"] = "attacker"; path.write_text(json.dumps(record))
    with pytest.raises(RuntimeError, match="signature"): validate_approval(path, "backup-a", "journal-a")
    payload = write_approval(path, "backup-a", "journal-a", "operator", ttl_seconds=30, target_database="restore_db")
    with pytest.raises(RuntimeError, match="expired"): validate_approval(path, "backup-a", "journal-a", now_epoch=payload["expires_at"] + 1)
    with pytest.raises(RuntimeError, match="independent"): require_recovery_ready(path, "backup-a", "journal-a")
    evidence = Path("artifacts/gate22d"); evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "validation.json").write_text(json.dumps({"schema":"gate22d-validation-v1","restore_approval":"passed","quarantine_fail_closed":"passed","secrets_included":False}) + "\n", encoding="utf-8")

def test_encrypted_backup_manifest_detects_tampering(tmp_path):
    from scripts.secure_backup import decrypt_for_restore, digest
    from scripts.secure_backup import _aes
    key = b"k" * 32; artifact = tmp_path / "backup.enc"; manifest = tmp_path / "backup.enc.json"; out = tmp_path / "plain.dump"
    import struct
    nonce = b"n" * 12; block = _aes(key).encrypt(nonce, b"disposable dump", b"0"); artifact.write_bytes(b"ATB1" + struct.pack("!I", len(block)) + nonce + block); manifest.write_text(json.dumps({"format":"agenttrust-encrypted-backup-v1","key_id":"v1","ciphertext_sha256":digest(artifact.read_bytes()),"encrypted":True}))
    decrypt_for_restore(artifact, manifest, key, out); assert out.read_bytes() == b"disposable dump"
    artifact.write_bytes(artifact.read_bytes() + b"tamper")
    with pytest.raises(RuntimeError, match="integrity"): decrypt_for_restore(artifact, manifest, key, out)
