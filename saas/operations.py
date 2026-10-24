"""Bounded, fail-closed operational maintenance primitives.

These helpers are intentionally storage-local and disposable-test friendly. They do
not connect to cloud storage or claim production RPO/RTO guarantees.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable


def _event(name: str, **fields: Any) -> dict[str, Any]:
    return {"event": name, "ts": time.time(), **fields}


def cleanup_backup_artifacts(root: Path, *, max_age_seconds: int, execute: bool = False,
                             protected: Iterable[Path] = ()) -> list[dict[str, Any]]:
    """Classify old encrypted backup artifacts; delete only with explicit execute."""
    if max_age_seconds < 1:
        raise ValueError("max_age_seconds must be positive")
    protected_paths = {path.resolve() for path in protected}
    cutoff = time.time() - max_age_seconds
    results: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.enc")) if root.exists() else []:
        resolved = path.resolve()
        if resolved in protected_paths:
            results.append(_event("backup_cleanup_skipped", path=path.name, reason="protected"))
            continue
        if path.stat().st_mtime >= cutoff:
            continue
        action = "deleted" if execute else "would_delete"
        if execute:
            path.unlink(missing_ok=True)
            manifest = path.with_suffix(path.suffix + ".json")
            manifest.unlink(missing_ok=True)
        results.append(_event("backup_cleanup", path=path.name, action=action))
    return results


def journal_integrity_report(journal: Any) -> dict[str, Any]:
    """Return sanitized journal verification evidence without tenant payloads."""
    events = journal.events()
    return {"event": "deletion_journal_verified", "count": len(events),
            "digest": hashlib.sha256("|".join(e["digest"] for e in events).encode()).hexdigest()}


def recovery_measurement(start: float, restore_finished: float, reconcile_finished: float,
                         backup_created: float, *, rto_objective_seconds: float,
                         max_recovery_point_age_seconds: float) -> dict[str, Any]:
    restore_seconds = restore_finished - start
    reconciliation_seconds = reconcile_finished - restore_finished
    total_seconds = reconcile_finished - start
    recovery_point_age_seconds = max(0.0, start - backup_created)
    return {
        "schema": "agenttrust-recovery-measurement-v1",
        "observed": {"restore_seconds": restore_seconds, "reconciliation_seconds": reconciliation_seconds,
                     "total_seconds": total_seconds, "recovery_point_age_seconds": recovery_point_age_seconds},
        "objectives": {"rto_seconds": rto_objective_seconds, "max_recovery_point_age_seconds": max_recovery_point_age_seconds},
        "within_objectives": total_seconds <= rto_objective_seconds and recovery_point_age_seconds <= max_recovery_point_age_seconds,
        "production_guarantee": False,
    }


def acquire_maintenance_lock(conn: Any, lock_name: str) -> bool:
    """Acquire a non-blocking PostgreSQL advisory lock for one maintenance worker."""
    row = conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))", ("agenttrust:maintenance:" + lock_name,)).fetchone()
    return bool(row and row[0])


def release_maintenance_lock(conn: Any, lock_name: str) -> None:
    conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", ("agenttrust:maintenance:" + lock_name,))
