"""Small PostgreSQL adapter; SQLite remains the deterministic local-test adapter."""
from __future__ import annotations
import json, os, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import psycopg

MIGRATION = Path(__file__).with_name("migrations") / "002_postgres.sql"
def now(): return datetime.now(timezone.utc)
def connect():
    url = os.getenv("AGENTTRUST_POSTGRES_URL", "").strip()
    if not url: raise RuntimeError("AGENTTRUST_POSTGRES_URL is required for the PostgreSQL adapter")
    conn = psycopg.connect(url); conn.execute(MIGRATION.read_text(encoding="utf-8")); return conn
def user_id(conn, issuer: str, subject: str) -> str:
    value = f"usr_{uuid.uuid5(uuid.NAMESPACE_URL, issuer + '|' + subject).hex}"
    conn.execute("INSERT INTO users (id,issuer,subject,created_at) VALUES (%s,%s,%s,%s) ON CONFLICT (issuer,subject) DO NOTHING", (value, issuer, subject, now())); return value
def require_membership(conn, organization_id: str, user: str, roles: tuple[str, ...] = ("owner","admin","member")) -> None:
    row = conn.execute("SELECT role FROM memberships WHERE organization_id=%s AND user_id=%s AND active=TRUE", (organization_id,user)).fetchone()
    if not row or row[0] not in roles: raise PermissionError("active organization membership required")
def create_run(conn, organization_id: str, user: str, project_id: str, idem: str, rows: list[dict[str, Any]], quota: int) -> dict[str, Any]:
    with conn.transaction():
        require_membership(conn, organization_id, user)
        project = conn.execute("SELECT id FROM projects WHERE id=%s AND organization_id=%s FOR SHARE", (project_id,organization_id)).fetchone()
        if not project: raise KeyError("project not found")
        existing = conn.execute("SELECT id,status,provider,sample_count FROM evaluation_runs WHERE organization_id=%s AND idempotency_key=%s", (organization_id,idem)).fetchone()
        if existing: return {"id": existing[0], "status": existing[1], "provider": existing[2], "sample_count": existing[3]}
        # Advisory lock serializes quota allocation per tenant without locking an
        # aggregate result; the idempotency UNIQUE constraint closes retry races.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (organization_id,))
        used = conn.execute("SELECT COALESCE(SUM(units),0) FROM usage_events WHERE organization_id=%s", (organization_id,)).fetchone()[0]
        if used + len(rows) > quota: raise PermissionError("evaluation quota exceeded")
        run_id = f"run_{uuid.uuid4().hex}"; ts = now()
        conn.execute("INSERT INTO evaluation_runs VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (run_id,organization_id,project_id,idem,"completed","mock",len(rows),ts))
        result={"run_id":run_id,"provider":"mock","benchmark_status":"mock","sample_count":len(rows),"evidence_note":"Local mock only; not production provider execution."}
        conn.execute("INSERT INTO evaluation_results VALUES (%s,%s,%s,%s,%s)", (run_id,organization_id,json.dumps(result),json.dumps({"provider":"mock"}),ts)); conn.execute("INSERT INTO usage_events VALUES (%s,%s,%s,%s,%s,%s,%s)",(f"use_{uuid.uuid4().hex}",organization_id,run_id,len(rows),0,idem,ts)); return {"id":run_id,"status":"completed","provider":"mock","sample_count":len(rows)}
