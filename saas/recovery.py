"""Fail-closed restore authorization and promotion controls."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _key() -> bytes:
    value = os.getenv("AGENTTRUST_RECOVERY_APPROVAL_KEY", "").encode()
    if len(value) < 32: raise RuntimeError("recovery approval key is unavailable")
    return value
def _sign(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(hmac.new(_key(), body, hashlib.sha256).digest()).decode()
def write_approval(path: Path, backup_digest: str, journal_digest: str, approved_by: str, ttl_seconds: int = 900, target_database: str = "", required_role: str = "recovery_operator") -> dict[str, Any]:
    approvers = {x.strip() for x in os.getenv("AGENTTRUST_RECOVERY_APPROVERS", "").split(",") if x.strip()}
    if approved_by not in approvers or not target_database or required_role != "recovery_operator" or ttl_seconds < 1 or ttl_seconds > 3600: raise RuntimeError("trusted recovery approval required")
    payload = {"operation_id": secrets.token_urlsafe(24), "backup_digest": backup_digest, "journal_digest": journal_digest, "approved_by": approved_by, "target_database": target_database, "required_role": required_role, "expires_at": datetime.now(timezone.utc).timestamp() + ttl_seconds, "consumed": False}
    record = {"payload": payload, "signature": _sign(payload)}
    tmp = path.with_suffix(path.suffix + ".tmp"); tmp.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8"); os.replace(tmp, path)
    return payload

def validate_approval(path: Path, backup_digest: str, journal_digest: str, now_epoch: float | None = None, target_database: str = "", consume: bool = False) -> dict[str, Any]:
    try: record = json.loads(path.read_text(encoding="utf-8")); payload = record["payload"]; signature = record["signature"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc: raise RuntimeError("restore approval unavailable") from exc
    if not hmac.compare_digest(str(signature), _sign(payload)): raise RuntimeError("restore approval signature invalid")
    if payload.get("consumed"): raise RuntimeError("restore approval replayed")
    if payload.get("backup_digest") != backup_digest or payload.get("journal_digest") != journal_digest: raise RuntimeError("restore approval digest mismatch")
    if target_database and payload.get("target_database") != target_database: raise RuntimeError("restore approval target mismatch")
    if payload.get("required_role") != "recovery_operator": raise RuntimeError("restore approval role invalid")
    if float(payload.get("expires_at", 0)) <= (now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp()): raise RuntimeError("restore approval expired")
    if consume:
        payload["consumed"] = True; path.write_text(json.dumps({"payload": payload, "signature": _sign(payload)}, sort_keys=True) + "\n", encoding="utf-8")
    return payload

def require_recovery_ready(approval_path: Path, backup_digest: str, journal_digest: str, journal_ok: bool | None = None, reconciled: bool | None = None, *, target_database: str = "", journal: Any = None, conn: Any = None, organization_id: str | None = None) -> dict[str, Any]:
    if journal is None or conn is None or not organization_id: raise RuntimeError("independent recovery evidence is required")
    matching = [e for e in journal.events() if e.get("organization_id") == organization_id]
    if len(matching) != 1: raise RuntimeError("independent deletion evidence is unavailable or conflicting")
    row = conn.execute("SELECT reconciled_at FROM tenant_restore_reconciliation WHERE organization_id=%s", (organization_id,)).fetchone()
    if not row or row[0] is None: raise RuntimeError("restored database is quarantined until reconciliation")
    return validate_approval(approval_path, backup_digest, journal_digest, target_database=target_database, consume=True)

class RecoveryOrchestrator:
    """Promotion gate executed against the actual restored target connection."""
    def __init__(self, conn: Any, journal: Any, approval_path: Path, target_database: str):
        self.conn, self.journal, self.approval_path, self.target_database = conn, journal, approval_path, target_database
    def promote(self, organization_id: str, backup_digest: str, journal_digest: str) -> dict[str, Any]:
        events = [e for e in self.journal.events() if e.get("organization_id") == organization_id]
        if len(events) != 1 or events[0].get("digest") != journal_digest: raise RuntimeError("independent deletion evidence is unavailable or conflicting")
        with self.conn.transaction():
            self.conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"recovery-promote:{self.target_database}:{organization_id}",))
            row = self.conn.execute("SELECT journal_digest,reconciled_at FROM tenant_restore_reconciliation WHERE organization_id=%s", (organization_id,)).fetchone()
            if not row or row[0] != journal_digest or row[1] is None: raise RuntimeError("restored database is quarantined until reconciliation")
            approval = validate_approval(self.approval_path, backup_digest, journal_digest, target_database=self.target_database)
            existing = self.conn.execute("SELECT status FROM recovery_promotions WHERE operation_id=%s", (approval["operation_id"],)).fetchone()
            if existing and existing[0] == "promoted": return {"promoted": True, "already_promoted": True, "operation_id": approval["operation_id"]}
            self.conn.execute("INSERT INTO recovery_promotions(operation_id,backup_digest,journal_digest,approved_by,expires_at,status,promoted_at) VALUES (%s,%s,%s,%s,to_timestamp(%s),'promoted',now()) ON CONFLICT (operation_id) DO NOTHING", (approval["operation_id"], backup_digest, journal_digest, approval["approved_by"], approval["expires_at"]))
            if not self.conn.execute("SELECT 1 FROM recovery_promotions WHERE operation_id=%s AND status='promoted'", (approval["operation_id"],)).fetchone(): raise RuntimeError("recovery promotion was not recorded")
        validate_approval(self.approval_path, backup_digest, journal_digest, target_database=self.target_database, consume=True)
        return {"promoted": True, "already_promoted": False, "operation_id": approval["operation_id"]}
