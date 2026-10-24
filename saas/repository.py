from __future__ import annotations
import json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = Path(__file__).with_name("migrations") / "001_initial.sql"
def now() -> str: return datetime.now(timezone.utc).isoformat()
def db_path() -> str: return os.getenv("AGENTTRUST_SAAS_DB", str(ROOT / "saas.sqlite3"))
def selected_backend() -> str:
    configured = os.getenv("AGENTTRUST_SAAS_BACKEND", "").strip().lower()
    if configured in {"postgres", "sqlite"}:
        if configured == "postgres" and not os.getenv("AGENTTRUST_POSTGRES_URL", "").strip():
            raise RuntimeError("PostgreSQL backend selected but AGENTTRUST_POSTGRES_URL is missing")
        if configured == "postgres" and os.getenv("AGENTTRUST_SAAS_DB", "").strip():
            raise RuntimeError("PostgreSQL backend selected with SQLite path configured")
        return configured
    if os.getenv("AGENTTRUST_SAAS_DB", "").strip(): return "sqlite"
    return "postgres" if os.getenv("AGENTTRUST_POSTGRES_URL", "").strip() else "sqlite"

def use_postgres() -> bool: return selected_backend() == "postgres"
def connect() -> sqlite3.Connection:
    if use_postgres():
        raise RuntimeError("SQLite connection unavailable while PostgreSQL backend is selected")
    conn = sqlite3.connect(db_path()); conn.row_factory = sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON"); conn.executescript(MIGRATION.read_text(encoding="utf-8")); conn.executescript("""
        CREATE TABLE IF NOT EXISTS evaluation_policies (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL, version INTEGER NOT NULL, name TEXT NOT NULL, schema_version TEXT NOT NULL, metrics_json TEXT NOT NULL, require_baseline INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (organization_id, project_id, name, version));
        CREATE TABLE IF NOT EXISTS evaluation_decisions (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL, current_run_id TEXT NOT NULL, baseline_run_id TEXT, policy_id TEXT NOT NULL, policy_version INTEGER NOT NULL, idempotency_key TEXT NOT NULL, decision TEXT NOT NULL CHECK (decision IN ('PASS','HOLD','INSUFFICIENT_EVIDENCE')), rationale_json TEXT NOT NULL, evidence_refs_json TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (organization_id, idempotency_key), UNIQUE (organization_id, current_run_id, policy_id));
    """); return conn
def new_id(prefix: str) -> str: return f"{prefix}_{uuid.uuid4().hex}"
def audit(conn, org_id: str, user_id: str, action: str, resource_type: str, resource_id: str) -> None:
    conn.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)", (new_id("aud"), org_id, user_id, action, resource_type, resource_id, now()))
def create_org(user_id: str, name: str) -> dict[str, Any]:
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return pg.create_org(conn, user_id, name)
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
        with pg.protected_connect() as conn: return pg.create_project(conn, org_id, user_id, name)
    conn=connect(); require_membership(conn,org_id,user_id,("owner","admin")); project_id=new_id("prj"); conn.execute("INSERT INTO projects VALUES (?,?,?,?)",(project_id,org_id,name,now())); audit(conn,org_id,user_id,"project.created","project",project_id); conn.commit(); return {"id":project_id,"organization_id":org_id,"name":name}
def project_for(conn, org_id: str, project_id: str): return conn.execute("SELECT * FROM projects WHERE id=? AND organization_id=?",(project_id,org_id)).fetchone()
def create_run(org_id: str, user_id: str, project_id: str, idem: str, rows: list[dict[str,Any]], quota: int) -> dict[str,Any]:
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return pg.create_run(conn, org_id, user_id, project_id, idem, rows, quota)
    conn=connect(); conn.execute("BEGIN IMMEDIATE"); require_membership(conn,org_id,user_id); project=project_for(conn,org_id,project_id)
    if project is None: raise KeyError("project not found")
    existing=conn.execute("SELECT * FROM evaluation_runs WHERE organization_id=? AND idempotency_key=?",(org_id,idem)).fetchone()
    if existing: return dict(existing)
    used=conn.execute("SELECT COALESCE(SUM(units),0) FROM usage_events WHERE organization_id=?",(org_id,)).fetchone()[0]
    if used+len(rows)>quota: raise PermissionError("evaluation quota exceeded")
    run_id=new_id("run"); ts=now(); conn.execute("INSERT INTO evaluation_runs VALUES (?,?,?,?,?,?,?,?)",(run_id,org_id,project_id,idem,"completed","mock",len(rows),ts)); result={"run_id":run_id,"provider":"mock","benchmark_status":"mock","sample_count":len(rows),"passed_cases":len(rows),"failed_cases":0,"outcome":"release","evidence_note":"Deterministic local mock evaluation; not a real provider or production benchmark."}
    recorded: dict[str, list[float]] = {}
    for row in rows:
        values = row.get("recorded_metrics") if isinstance(row, dict) else None
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(key, str) and isinstance(value, (int, float)) and not isinstance(value, bool):
                    recorded.setdefault(key, []).append(float(value))
    quality = {key: sum(values) / len(values) for key, values in recorded.items() if values}
    if quality:
        result["quality_metrics"] = quality
        result["quality_metrics_source"] = "explicitly recorded synthetic evaluation input"
    conn.execute("INSERT INTO evaluation_results VALUES (?,?,?,?,?)",(run_id,org_id,json.dumps(result),json.dumps({"source":"saas-vertical-slice","provider":"mock","git_sha":os.getenv("GIT_COMMIT_SHA","unknown")}),ts)); conn.execute("INSERT INTO usage_events VALUES (?,?,?,?,?,?,?)",(new_id("use"),org_id,run_id,len(rows),0.0,idem,ts)); audit(conn,org_id,user_id,"evaluation.completed","evaluation_run",run_id); conn.commit(); return {"id":run_id,"status":"completed","provider":"mock","sample_count":len(rows),"outcome":"release"}
def get_run(org_id: str, user_id: str, run_id: str) -> dict[str,Any] | None:
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return pg.get_run(conn, org_id, user_id, run_id)
    conn=connect(); require_membership(conn,org_id,user_id); row=conn.execute("SELECT r.*, e.result_json, e.evidence_metadata_json FROM evaluation_runs r LEFT JOIN evaluation_results e ON e.run_id=r.id WHERE r.id=? AND r.organization_id=?",(run_id,org_id)).fetchone(); return dict(row) if row else None

def list_orgs(user_id: str) -> list[dict[str, Any]]:
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return pg.list_orgs(conn, user_id)
    conn = connect()
    rows = conn.execute("SELECT o.id,o.name,m.role FROM organizations o JOIN memberships m ON m.organization_id=o.id WHERE m.user_id=? ORDER BY o.name", (user_id,)).fetchall()
    return [dict(row) for row in rows]

def list_projects(org_id: str, user_id: str) -> list[dict[str, Any]]:
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return pg.list_projects(conn, org_id, user_id)
    conn = connect(); require_membership(conn, org_id, user_id)
    return [dict(row) for row in conn.execute("SELECT id,organization_id,name FROM projects WHERE organization_id=? ORDER BY name", (org_id,)).fetchall()]

def list_runs(org_id: str, user_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
    return search_runs(org_id, user_id, project_id)["evaluations"]

def search_runs(org_id: str, user_id: str, project_id: str | None = None, search: str = "", status: str = "", page: int = 1, page_size: int = 20) -> dict[str, Any]:
    page = max(1, page); page_size = min(100, max(1, page_size)); offset = (page - 1) * page_size
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return pg.search_runs(conn, org_id, user_id, project_id, search, status, page, page_size)
    conn = connect(); require_membership(conn, org_id, user_id)
    clauses = ["organization_id=?"]; params: list[Any] = [org_id]
    if project_id: clauses.append("project_id=?"); params.append(project_id)
    if search: clauses.append("(id LIKE ? OR provider LIKE ? OR status LIKE ?)"); params.extend([f"%{search}%"] * 3)
    if status: clauses.append("status=?"); params.append(status)
    where = " AND ".join(clauses)
    total = conn.execute(f"SELECT COUNT(*) FROM evaluation_runs WHERE {where}", tuple(params)).fetchone()[0]
    rows = conn.execute(f"SELECT id,project_id,status,provider,sample_count,created_at FROM evaluation_runs WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?", tuple(params + [page_size, offset])).fetchall()
    return {"evaluations": [dict(row) for row in rows], "page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}

def create_policy(org_id: str, project_id: str, user_id: str, body: dict[str, Any]) -> dict[str, Any]:
    from . import decision_engine as de
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return de.create_policy_pg(conn, org_id, project_id, user_id, body)
    conn = connect()
    return de.create_policy_sqlite(conn, org_id, project_id, user_id, body)

def list_policies(org_id: str, project_id: str, user_id: str) -> list[dict[str, Any]]:
    from . import decision_engine as de
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn:
            de._require_membership(conn, org_id, user_id, postgres=True)
            rows = conn.execute("SELECT id,project_id,version,name,schema_version,metrics_json,require_baseline,created_by,created_at FROM evaluation_policies WHERE organization_id=%s AND project_id=%s ORDER BY name,version DESC", (org_id, project_id)).fetchall()
    else:
        conn = connect(); de._require_membership(conn, org_id, user_id, postgres=False)
        rows = conn.execute("SELECT id,project_id,version,name,schema_version,metrics_json,require_baseline,created_by,created_at FROM evaluation_policies WHERE organization_id=? AND project_id=? ORDER BY name,version DESC", (org_id, project_id)).fetchall()
    keys = ["id","project_id","version","name","schema_version","metrics_json","require_baseline","created_by","created_at"]
    result = []
    for row in rows:
        item = dict(zip(keys, tuple(row))); item["metrics"] = json.loads(item.pop("metrics_json")); result.append(item)
    return result

def create_decision(org_id: str, current_run_id: str, user_id: str, body: dict[str, Any]) -> dict[str, Any]:
    from . import decision_engine as de
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return de.create_decision_pg(conn, org_id, current_run_id, user_id, body)
    conn = connect()
    return de.create_decision_sqlite(conn, org_id, current_run_id, user_id, body)

def list_decisions(org_id: str, user_id: str, project_id: str | None = None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    from . import decision_engine as de
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return de.list_decisions(conn, org_id, user_id, project_id, page, page_size, True)
    conn = connect(); return de.list_decisions(conn, org_id, user_id, project_id, page, page_size, False)

def get_decision(org_id: str, user_id: str, decision_id: str) -> dict[str, Any]:
    from . import decision_engine as de
    if use_postgres():
        from . import postgres_repository as pg
        with pg.protected_connect() as conn: return de.get_decision_pg(conn, org_id, user_id, decision_id)
    conn = connect(); return de.get_decision_sqlite(conn, org_id, user_id, decision_id)

