"""Tenant export, retention, and deletion primitives for PostgreSQL only."""
from __future__ import annotations
import hashlib, json, os, uuid
from datetime import datetime, timedelta, timezone
from typing import Any

EXPORT_VERSION = "agenttrust-tenant-export-v1"
TABLES = ("organizations", "memberships", "projects", "evaluation_runs", "evaluation_results", "usage_events", "audit_events")
TENANT_COLUMNS = {"organizations": "id", "memberships": "organization_id", "projects": "organization_id", "evaluation_runs": "organization_id", "evaluation_results": "organization_id", "usage_events": "organization_id", "audit_events": "organization_id"}

def _now(): return datetime.now(timezone.utc)
def _audit(conn, org_id: str, actor: str | None, action: str, details: dict[str, Any] | None = None) -> None:
    conn.execute("INSERT INTO tenant_lifecycle_audit VALUES (%s,%s,%s,%s,%s,%s)", (f"lca_{uuid.uuid4().hex}", org_id, actor, action, json.dumps(details or {}, sort_keys=True), _now()))
def _member(conn, org_id: str, user_id: str, roles: tuple[str, ...]) -> str:
    row = conn.execute("SELECT role FROM memberships WHERE organization_id=%s AND user_id=%s AND active=TRUE", (org_id, user_id)).fetchone()
    if not row or row[0] not in roles: raise PermissionError("active organization membership required")
    return row[0]

class DeletionJournal:
    """Append-only independent deletion evidence; contains no tenant payload or secrets."""
    def __init__(self, path): self.path = path
    def append(self, organization_id: str, actor_user_id: str) -> dict[str, str]:
        previous = ""
        if self.path.exists():
            lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line]
            if lines: previous = json.loads(lines[-1])["digest"]
        event = {"event_id": f"del_{uuid.uuid4().hex}", "organization_id": organization_id, "actor_user_id": actor_user_id, "occurred_at": _now().isoformat(), "previous_digest": previous}
        event["digest"] = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle: handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event
    def events(self) -> list[dict[str, str]]:
        if not self.path.exists(): raise RuntimeError("independent deletion journal unavailable")
        events, previous, organizations = [], "", set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line); digest = event.pop("digest", None)
            if event.get("previous_digest", "") != previous or hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != digest: raise RuntimeError("deletion journal integrity failure")
            if event.get("organization_id") in organizations: raise RuntimeError("conflicting duplicate deletion event")
            event["digest"] = digest; events.append(event); previous = digest
            organizations.add(event.get("organization_id"))
        return events

def reconcile_restored_tenant(conn, journal: DeletionJournal, organization_id: str) -> dict[str, Any]:
    events = [event for event in journal.events() if event.get("organization_id") == organization_id]
    if not events: raise RuntimeError("no independent deletion evidence for restored tenant")
    event = events[-1]
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"tenant-reconcile:{organization_id}",))
        existing = conn.execute("SELECT journal_digest FROM tenant_restore_reconciliation WHERE organization_id=%s", (organization_id,)).fetchone()
        if existing and existing[0] == event["digest"]: return {"organization_id": organization_id, "reconciled": True, "already_reconciled": True}
        for table in ("evaluation_results", "usage_events", "evaluation_runs", "projects", "memberships"): conn.execute(f"DELETE FROM {table} WHERE organization_id=%s", (organization_id,))
        conn.execute("UPDATE organizations SET name='[deleted tenant]', deleted_at=now() WHERE id=%s", (organization_id,))
        conn.execute("INSERT INTO tenant_restore_reconciliation VALUES (%s,%s,now()) ON CONFLICT (organization_id) DO UPDATE SET journal_digest=EXCLUDED.journal_digest,reconciled_at=EXCLUDED.reconciled_at", (organization_id, event["digest"]))
    return {"organization_id": organization_id, "reconciled": True, "already_reconciled": False}

def restore_access_allowed(conn, organization_id: str) -> bool:
    return conn.execute("SELECT 1 FROM tenant_restore_reconciliation r JOIN recovery_promotions p ON p.journal_digest=r.journal_digest WHERE r.organization_id=%s AND p.status='promoted' AND p.expires_at>now()", (organization_id,)).fetchone() is not None

def export_tenant(conn, org_id: str, actor: str, *, elevated: bool = False) -> dict[str, Any]:
    role = _member(conn, org_id, actor, ("owner", "admin"))
    with conn.transaction():
        org = conn.execute("SELECT id,name,created_at,deleted_at FROM organizations WHERE id=%s", (org_id,)).fetchone()
        if not org: raise KeyError("organization not found")
        rows: dict[str, list[dict[str, Any]]] = {}
        for table in TABLES:
            cursor = conn.execute(f"SELECT * FROM {table} WHERE {TENANT_COLUMNS[table]}=%s", (org_id,))
            columns = [item.name for item in cursor.description]
            rows[table] = [dict(zip(columns, row)) for row in cursor.fetchall()]
        _audit(conn, org_id, actor, "export.requested", {"role": role})
        result = {"schema": EXPORT_VERSION, "manifest": {"organization_id": org_id, "tables": TABLES, "record_counts": {key: len(value) for key, value in rows.items()}, "excluded": ["sessions", "oidc_login_states", "Fernet keys", "raw bearer tokens", "PKCE verifiers"]}, "organization": dict(zip(("id","name","created_at","deleted_at"), org)), "records": rows}
        _audit(conn, org_id, actor, "export.completed", result["manifest"])
        return result

def cleanup_expired(conn, *, retention_days: int | None = None, dry_run: bool = False) -> dict[str, int | bool]:
    days = retention_days if retention_days is not None else int(os.getenv("AGENTTRUST_RETENTION_DAYS", "30"))
    if days < 1 or days > 3650: raise ValueError("retention days must be between 1 and 3650")
    cutoff = _now() - timedelta(days=days)
    with conn.transaction():
        sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE expires_at < %s", (cutoff,)).fetchone()[0]
        states = conn.execute("SELECT COUNT(*) FROM oidc_login_states WHERE expires_at < %s", (cutoff,)).fetchone()[0]
        if not dry_run:
            conn.execute("DELETE FROM sessions WHERE expires_at < %s", (cutoff,))
            conn.execute("DELETE FROM oidc_login_states WHERE expires_at < %s", (cutoff,))
        return {"dry_run": dry_run, "sessions": sessions, "oidc_login_states": states}

def delete_tenant(conn, org_id: str, actor: str, confirmation: str, *, fail_after: str | None = None) -> dict[str, Any]:
    if confirmation != f"DELETE {org_id}": raise PermissionError("explicit deletion confirmation required")
    with conn.transaction():
        already = conn.execute("SELECT 1 FROM organizations WHERE id=%s AND deleted_at IS NOT NULL", (org_id,)).fetchone()
        if already and conn.execute("SELECT 1 FROM tenant_lifecycle_audit WHERE organization_id=%s AND actor_user_id=%s AND action='deletion.completed'", (org_id, actor)).fetchone():
            return {"organization_id": org_id, "deleted": True, "already_deleted": True, "audit_tombstone": True}
        role = _member(conn, org_id, actor, ("owner",))
        if not conn.execute("SELECT 1 FROM organizations WHERE id=%s AND deleted_at IS NULL FOR UPDATE", (org_id,)).fetchone(): raise KeyError("organization not found")
        _audit(conn, org_id, actor, "deletion.requested", {"role": role})
        conn.execute("DELETE FROM evaluation_results WHERE organization_id=%s", (org_id,))
        conn.execute("DELETE FROM usage_events WHERE organization_id=%s", (org_id,))
        conn.execute("DELETE FROM evaluation_runs WHERE organization_id=%s", (org_id,))
        conn.execute("DELETE FROM projects WHERE organization_id=%s", (org_id,))
        conn.execute("DELETE FROM memberships WHERE organization_id=%s", (org_id,))
        if fail_after == "children": raise RuntimeError("controlled deletion interruption")
        conn.execute("UPDATE organizations SET name='[deleted tenant]', deleted_at=now() WHERE id=%s", (org_id,))
        _audit(conn, org_id, actor, "deletion.completed", {"retained_audit_tombstone": True})
        return {"organization_id": org_id, "deleted": True, "audit_tombstone": True}
