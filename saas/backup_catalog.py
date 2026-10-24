"""Sanitized backup catalog and local object-lock semantics for disposable tests."""
from __future__ import annotations
import hashlib, json, time
from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True)
class BackupRecord:
    backup_id: str
    key_id: str
    ciphertext_digest: str
    created_at: float
    retain_until: float
    legal_hold: bool = False
class LocalBackupCatalog:
    """Local simulation only; filesystem immutability is not production evidence."""
    def __init__(self, path: Path): self.path = path
    def put(self, record: BackupRecord) -> None:
        if len(record.ciphertext_digest) != 64 or any(c not in "0123456789abcdef" for c in record.ciphertext_digest.lower()): raise RuntimeError("backup digest is malformed")
        if record.retain_until < record.created_at: raise RuntimeError("retention metadata is invalid")
        if self.path.exists():
            existing = self.get(record.backup_id)
            if existing != record: raise RuntimeError("protected backup catalog entry cannot be overwritten")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True); self.path.write_text(json.dumps(record.__dict__, sort_keys=True) + "\n", encoding="utf-8")
    def get(self, backup_id: str) -> BackupRecord:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if set(data) != {"backup_id", "key_id", "ciphertext_digest", "created_at", "retain_until", "legal_hold"}: raise RuntimeError("backup catalog metadata is malformed")
        if data["backup_id"] != backup_id: raise RuntimeError("backup identity mismatch")
        return BackupRecord(**data)
    def can_delete(self, record: BackupRecord, *, now: float | None = None) -> bool:
        return not record.legal_hold and (now if now is not None else time.time()) >= record.retain_until
def catalog_digest(record: BackupRecord) -> str:
    return hashlib.sha256(json.dumps(record.__dict__, sort_keys=True).encode()).hexdigest()

