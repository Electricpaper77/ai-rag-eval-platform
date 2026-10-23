from __future__ import annotations
import json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = Path(__file__).with_name("migrations") / "001_initial.sql"
def now() -> str: return datetime.now(timezone.utc).isoformat()
def db_path() -> str: return os.getenv("AGENTTRUST_SAAS_DB", str(ROOT / "saas.sqlite3"))
def use_postgres() -> bool:
    return bool(os.getenv("AGENTTRUST_POSTGRES_URL", "").strip()) and os.getenv("AGENTTRUST_SAAS_RUNTIME_MODE", "production").strip().lower() not in ("local", "test")
def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path()); conn.row_factory = sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON"); conn.executescript(MIGRATION.read_text(encoding="utf-8")); return conn
def new_id(prefix: str) -> str: return f"{prefix}_{uuid.uuid4().hex}"
def audit(conn, org_id: str, user_id: str, action: str, resource_type: str, resource_id: str) -> None:
    conn.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)", (new_id("aud"), org_id, user_id, action, resource_type, resource_id, now()))
def create_org(user_id: str, name: str) -> dict[str, Any]:
    if use_postgres():
        from . import postgres_repository as pg
        return pg.create_org(pg.connect(), user_id, name)
    org_id=new_id("org"); conn=connect(); conn.execute("INSERT INTO organizations VALUES (?,?,?)",(org_id,name,now())); conn.execute("INSERT INTO memberships VALUES (?,?,?,?)",(org_id,user_id,"owner",now())); audit(conn,org_id,user_id,"organization.created","organization",org_id); conn.commit(); return {"id":org_id,"name":name,"role":"owner"}
def membership(conn, org_id: str, user_id: str): return conn.execute("SELECT * FROM memberships WHERE organization_id=? AND user_id=?",(org_id,user_id)).fetchone()
def require_membership(conn, org_id: str, user_id: str, roles: tuple[str, ...] | None = None):
    row = membership(conn, org_id, user_id)
    if row is None or (roles is not None and row["role"] not in roles):
        raise PermissionError("organization membership required")
    return row
def create_project(org_id: str, user_id: str, name: str) -> dict[str, Any]:
    if use_postgres():
        from . import postgres_repository as pg
        return pg.create_project(pg.connect(), org_id, user_id, name)
    conn=connect(); require_membership(conn,org_id,user_id,("owner","admin")); project_id=new_id("prj"); conn.execute("INSERT INTO projects VALUES (?,?,?,?)",(project_id,org_id,name,now())); audit(conn,org_id,user_id,"project.created","project",project_id); conn.commit(); return {"id":project_id,"organization_id":org_id,"name":name}
def project_for(conn, org_id: str, project_id: str): return conn.execute("SELECT * FROM projects WHERE id=? AND organization_id=?",(project_id,org_id)).fetchone()
def create_run(org_id: str, user_id: str, project_id: str, idem: str, rows: list[dict[str,Any]], quota: int) -> dict[str,Any]:
    if use_postgres():
        from . import postgres_repository as pg
        return pg.create_run(pg.connect(), org_id, user_id, project_id, idem, rows, quota)
    conn=connect(); conn.execute("BEGIN IMMEDIATE"); require_membership(conn,org_id,user_id); project=project_for(conn,org_id,project_id)
    if project is None: raise KeyError("project not found")
    existing=conn.execute("SELECT * FROM evaluation_runs WHERE organization_id=? AND idempotency_key=?",(org_id,idem)).fetchone()
    if existing: return dict(existing)
    used=conn.execute("SELECT COALESCE(SUM(units),0) FROM usage_events WHERE organization_id=?",(org_id,)).fetchone()[0]
    if used+len(rows)>quota: raise PermissionError("evaluation quota exceeded")
    run_id=new_id("run"); ts=now(); conn.execute("INSERT INTO evaluation_runs VALUES (?,?,?,?,?,?,?,?)",(run_id,org_id,project_id,idem,"completed","mock",len(rows),ts)); result={"run_id":run_id,"provider":"mock","benchmark_status":"mock","sample_count":len(rows),"passed_cases":len(rows),"failed_cases":0,"outcome":"release","evidence_note":"Deterministic local mock evaluation; not a real provider or production benchmark."}; conn.execute("INSERT INTO evaluation_results VALUES (?,?,?,?,?)",(run_id,org_id,json.dumps(result),json.dumps({"source":"saas-vertical-slice","provider":"mock","git_sha":os.getenv("GIT_COMMIT_SHA","unknown")}),ts)); conn.execute("INSERT INTO usage_events VALUES (?,?,?,?,?,?,?)",(new_id("use"),org_id,run_id,len(rows),0.0,idem,ts)); audit(conn,org_id,user_id,"evaluation.completed","evaluation_run",run_id); conn.commit(); return {"id":run_id,"status":"completed","provider":"mock","sample_count":len(rows),"outcome":"release"}
def get_run(org_id: str, user_id: str, run_id: str) -> dict[str,Any] | None:
    if use_postgres():
        from . import postgres_repository as pg
        return pg.get_run(pg.connect(), org_id, user_id, run_id)
    conn=connect(); require_membership(conn,org_id,user_id); row=conn.execute("SELECT r.*, e.result_json, e.evidence_metadata_json FROM evaluation_runs r LEFT JOIN evaluation_results e ON e.run_id=r.id WHERE r.id=? AND r.organization_id=?",(run_id,org_id)).fetchone(); return dict(row) if row else None
