"""Provider-neutral encryption-key custody boundary."""
from __future__ import annotations
import hashlib, hmac
from dataclasses import dataclass
from typing import Mapping
@dataclass(frozen=True)
class KeyRecord:
    key_id: str
    purpose: str
    state: str = "active"
class KeyProvider:
    def key_identity(self, key_id: str) -> KeyRecord: raise NotImplementedError
    def encrypt_key(self, key_id: str, purpose: str) -> bytes: raise NotImplementedError
    def decrypt_key(self, key_id: str, purpose: str) -> bytes: raise NotImplementedError
class DisposableKeyProvider(KeyProvider):
    """Synthetic in-memory provider; never use for deployment secrets."""
    def __init__(self, keys: Mapping[str, bytes], *, purpose: str = "backup"):
        self._keys = dict(keys); self._purpose = purpose; self._states = {k: "active" for k in self._keys}
    def key_identity(self, key_id: str) -> KeyRecord:
        if key_id not in self._keys: raise KeyError("unknown encryption key")
        return KeyRecord(key_id, self._purpose, self._states[key_id])
    def retire(self, key_id: str) -> None: self.key_identity(key_id); self._states[key_id] = "retired"
    def revoke(self, key_id: str) -> None: self.key_identity(key_id); self._states[key_id] = "revoked"
    def destroy(self, key_id: str) -> None: self.key_identity(key_id); self._states[key_id] = "destroyed"; del self._keys[key_id]
    def encrypt_key(self, key_id: str, purpose: str) -> bytes: return self._get(key_id, purpose, False)
    def decrypt_key(self, key_id: str, purpose: str) -> bytes: return self._get(key_id, purpose, True)
    def _get(self, key_id: str, purpose: str, allow_retired: bool) -> bytes:
        record = self.key_identity(key_id)
        if record.purpose != purpose or record.state in {"revoked", "destroyed"} or (record.state == "retired" and not allow_retired): raise RuntimeError("encryption key is unavailable")
        return bytes(self._keys[key_id])
    def key_fingerprint(self, key_id: str) -> str: return hashlib.sha256(self.key_identity(key_id).key_id.encode()).hexdigest()[:16]
def require_distinct_approval_roles(requester: str, approver: str, *, approver_role: str) -> None:
    if not requester or not approver or hmac.compare_digest(requester, approver) or approver_role != "recovery_approver": raise RuntimeError("restore approval requires separation of duties")

