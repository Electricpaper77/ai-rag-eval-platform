"""Fail-closed restore authorization and promotion controls.

Restore databases are quarantined until independent deletion evidence and a
short-lived approval are both validated. This module never promotes a database
or handles customer data itself.
"""
from __future__ import annotations
import hashlib, json, secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def write_approval(path: Path, backup_digest: str, journal_digest: str, approved_by: str, ttl_seconds: int = 900) -> dict[str, Any]:
    if not approved_by or ttl_seconds < 1 or ttl_seconds > 3600: raise ValueError("invalid restore approval")
    payload = {"operation_id": secrets.token_urlsafe(24), "backup_digest": backup_digest, "journal_digest": journal_digest, "approved_by": approved_by, "expires_at": (datetime.now(timezone.utc).timestamp() + ttl_seconds)}
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return payload

def validate_approval(path: Path, backup_digest: str, journal_digest: str, now_epoch: float | None = None) -> dict[str, Any]:
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise RuntimeError("restore approval unavailable") from exc
    if not all(isinstance(payload.get(k), str) and payload[k] for k in ("operation_id", "backup_digest", "journal_digest", "approved_by")):
        raise RuntimeError("restore approval malformed")
    if payload["backup_digest"] != backup_digest or payload["journal_digest"] != journal_digest:
        raise RuntimeError("restore approval digest mismatch")
    if float(payload.get("expires_at", 0)) <= (now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp()):
        raise RuntimeError("restore approval expired")
    return payload

def require_recovery_ready(approval_path: Path, backup_digest: str, journal_digest: str, journal_ok: bool, reconciled: bool) -> dict[str, Any]:
    if not journal_ok: raise RuntimeError("independent deletion journal is unavailable or corrupt")
    if not reconciled: raise RuntimeError("restored database is quarantined until reconciliation")
    return validate_approval(approval_path, backup_digest, journal_digest)
