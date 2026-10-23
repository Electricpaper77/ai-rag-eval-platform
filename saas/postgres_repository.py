"""Small PostgreSQL adapter; SQLite remains the deterministic local-test adapter."""
from __future__ import annotations
import hashlib, json, os, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import psycopg
from cryptography.fernet import Fernet, InvalidToken

MIGRATIONS = [Path(__file__).with_name("migrations") / name for name in ("002_postgres.sql", "003_lifecycle.sql", "004_recovery_controls.sql")]
def now(): return datetime.now(timezone.utc)
def migrate():
    """Apply the versioned PostgreSQL baseline once, outside request paths."""
    url = os.getenv("AGENTTRUST_POSTGRES_URL", "").strip()
    if not url: raise RuntimeError("AGENTTRUST_POSTGRES_URL is required for the PostgreSQL adapter")
    with psycopg.connect(url) as conn:
        conn.execute("SET lock_timeout = '5s'")
        conn.execute("SET statement_timeout = '30s'")
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('agenttrust:migrations'))")
            conn.execute("""CREATE TABLE IF NOT EXISTS agenttrust_schema_migrations (
                version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
            applied = {row[0]: row[1] for row in conn.execute(
                "SELECT version, checksum FROM agenttrust_schema_migrations ORDER BY version"
            )}
            expected_versions = [int(path.stem.split("_")[0]) for path in MIGRATIONS]
            if applied and sorted(applied) != list(range(min(applied), max(applied) + 1)):
                raise RuntimeError("PostgreSQL migration history is missing or out of order")
            for path in MIGRATIONS:
                version = int(path.stem.split("_")[0])
                checksum = hashlib.sha256(path.read_bytes()).hexdigest()
                if version in applied:
                    if applied[version] != checksum:
                        raise RuntimeError(f"PostgreSQL migration checksum mismatch: {version}")
                    continue
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO agenttrust_schema_migrations(version, checksum) VALUES (%s,%s)", (version, checksum))

def connect():
    url = os.getenv("AGENTTRUST_POSTGRES_URL", "").strip()
    if not url: raise RuntimeError("AGENTTRUST_POSTGRES_URL is required for the PostgreSQL adapter")
    conn = psycopg.connect(url)
    # Keep integration work bounded; callers still own transaction boundaries.
    conn.execute("SET lock_timeout = '5s'")
    conn.execute("SET statement_timeout = '15s'")
    conn.commit()
    return conn
def user_id(conn, issuer: str, subject: str) -> str:
    value = f"usr_{uuid.uuid5(uuid.NAMESPACE_URL, issuer + '|' + subject).hex}"
    conn.execute("INSERT INTO users (id,issuer,subject,created_at) VALUES (%s,%s,%s,%s) ON CONFLICT (issuer,subject) DO NOTHING", (value, issuer, subject, now())); return value

def hash_secret(value: str) -> str: return hashlib.sha256(value.encode()).hexdigest()

class PostgresSessionStore:
    def __init__(self, connection_factory): self.connection_factory = connection_factory
    def put(self, sid: str, user: dict[str, str], expires_at: float, csrf: str) -> None:
        with self.connection_factory() as conn:
            with conn.transaction():
                uid = user_id(conn, user["issuer"], user["subject"])
                conn.execute("INSERT INTO sessions VALUES (%s,%s,%s,%s,%s,to_timestamp(%s),NULL,%s)", (hash_secret(sid), uid, user["issuer"], user["subject"], hash_secret(csrf), expires_at, now()))
    def get(self, sid: str, csrf: str | None = None) -> dict[str, str] | None:
        with self.connection_factory() as conn:
            row = conn.execute("SELECT user_id,issuer,subject,expires_at,csrf_hash FROM sessions WHERE session_hash=%s AND revoked_at IS NULL AND expires_at>now()", (hash_secret(sid),)).fetchone()
        if not row or (csrf is not None and not secrets_equal(hash_secret(csrf), row[4])): return None
        return {"user_id": row[0], "issuer": row[1], "subject": row[2], "csrf": csrf or ""}
    def revoke(self, sid: str) -> None:
        with self.connection_factory() as conn:
            conn.execute("UPDATE sessions SET revoked_at=now() WHERE session_hash=%s", (hash_secret(sid),)); conn.commit()


class PostgresLoginStateStore:
    """Shared, expiring OIDC state with one-time transactional consumption."""
    def __init__(self, connection_factory, encryption_key: bytes, key_id: str = "v1", historical_keys: dict[str, bytes] | None = None):
        self.connection_factory = connection_factory
        if not key_id or ":" in key_id or not key_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError("invalid OIDC state encryption key id")
        self.key_id = key_id
        self.keys = {key_id: Fernet(encryption_key)}
        for historical_id, historical_key in (historical_keys or {}).items():
            if historical_id in self.keys or not historical_id or ":" in historical_id:
                raise ValueError("duplicate OIDC state encryption key id")
            self.keys[historical_id] = Fernet(historical_key)

    def put(self, state: str, item: dict[str, object], config, expires_at: float) -> None:
        payload = f"at1:{self.key_id}:" + self.keys[self.key_id].encrypt(json.dumps(item, separators=(",", ":")).encode()).decode()
        with self.connection_factory() as conn:
            with conn.transaction():
                conn.execute(
                    "INSERT INTO oidc_login_states VALUES (%s,%s,%s,%s,%s,to_timestamp(%s),%s)",
                    (hash_secret(state), config.issuer, config.client_id, config.redirect_uri, payload, expires_at, now()),
                )

    def consume(self, state: str, config, now_epoch: float | None = None) -> dict[str, object]:
        with self.connection_factory() as conn:
            with conn.transaction():
                row = conn.execute(
                    "DELETE FROM oidc_login_states WHERE state_hash=%s AND issuer=%s AND client_id=%s AND redirect_uri=%s AND expires_at>now() RETURNING payload_encrypted",
                    (hash_secret(state), config.issuer, config.client_id, config.redirect_uri),
                ).fetchone()
        if not row:
            raise ValueError("invalid, expired, or mismatched OIDC login state")
        try:
            raw = bytes(row[0]).decode()
            if raw.startswith("at1:"):
                _, key_id, token = raw.split(":", 2)
                fernet = self.keys.get(key_id)
                if fernet is None: raise ValueError("unknown OIDC state encryption key id")
                item = json.loads(fernet.decrypt(token.encode()).decode())
            else:  # bounded compatibility for pre-rotation rows
                item = json.loads(self.keys[self.key_id].decrypt(bytes(row[0])).decode())
        except (InvalidToken, ValueError, TypeError) as exc:
            raise ValueError("invalid OIDC login state payload") from exc
        if now_epoch is not None and float(item["expires_at"]) < now_epoch:
            raise ValueError("expired OIDC login state")
        return item

    def cleanup(self) -> int:
        with self.connection_factory() as conn:
            with conn.transaction():
                return conn.execute("DELETE FROM oidc_login_states WHERE expires_at<=now()").rowcount

def secrets_equal(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a, b)
def require_membership(conn, organization_id: str, user: str, roles: tuple[str, ...] = ("owner","admin","member")) -> None:
    row = conn.execute("SELECT role FROM memberships WHERE organization_id=%s AND user_id=%s AND active=TRUE", (organization_id,user)).fetchone()
    if not row or row[0] not in roles: raise PermissionError("active organization membership required")

def create_org(conn, user: str, name: str) -> dict[str, Any]:
    with conn.transaction():
        org = f"org_{uuid.uuid4().hex}"
        conn.execute("INSERT INTO organizations VALUES (%s,%s,%s)", (org, name, now()))
        conn.execute("INSERT INTO memberships VALUES (%s,%s,'owner',TRUE,%s)", (org, user, now()))
    return {"id": org, "name": name, "role": "owner"}

def create_project(conn, organization_id: str, user: str, name: str) -> dict[str, Any]:
    with conn.transaction():
        require_membership(conn, organization_id, user, ("owner", "admin"))
        project = f"prj_{uuid.uuid4().hex}"
        conn.execute("INSERT INTO projects VALUES (%s,%s,%s,%s)", (project, organization_id, name, now()))
    return {"id": project, "organization_id": organization_id, "name": name}
def create_run(conn, organization_id: str, user: str, project_id: str, idem: str, rows: list[dict[str, Any]], quota: int) -> dict[str, Any]:
    with conn.transaction():
        require_membership(conn, organization_id, user)
        # Serialize the idempotency lookup with quota allocation.  The lookup
        # must be repeated under the tenant lock so two retries resolve to the
        # same committed run instead of racing into a unique-key error.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (organization_id,))
        project = conn.execute("SELECT id FROM projects WHERE id=%s AND organization_id=%s FOR SHARE", (project_id,organization_id)).fetchone()
        if not project: raise KeyError("project not found")
        existing = conn.execute("SELECT id,status,provider,sample_count FROM evaluation_runs WHERE organization_id=%s AND idempotency_key=%s", (organization_id,idem)).fetchone()
        if existing: return {"id": existing[0], "status": existing[1], "provider": existing[2], "sample_count": existing[3]}
        used = conn.execute("SELECT COALESCE(SUM(units),0) FROM usage_events WHERE organization_id=%s", (organization_id,)).fetchone()[0]
        if used + len(rows) > quota: raise PermissionError("evaluation quota exceeded")
        run_id = f"run_{uuid.uuid4().hex}"; ts = now()
        conn.execute("INSERT INTO evaluation_runs VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (run_id,organization_id,project_id,idem,"completed","mock",len(rows),ts))
        result={"run_id":run_id,"provider":"mock","benchmark_status":"mock","sample_count":len(rows),"evidence_note":"Local mock only; not production provider execution."}
        conn.execute("INSERT INTO evaluation_results VALUES (%s,%s,%s,%s,%s)", (run_id,organization_id,json.dumps(result),json.dumps({"provider":"mock"}),ts)); conn.execute("INSERT INTO usage_events VALUES (%s,%s,%s,%s,%s,%s,%s)",(f"use_{uuid.uuid4().hex}",organization_id,run_id,len(rows),0,idem,ts)); return {"id":run_id,"status":"completed","provider":"mock","sample_count":len(rows)}

def get_run(conn, organization_id: str, user: str, run_id: str) -> dict[str, Any] | None:
    with conn.transaction():
        require_membership(conn, organization_id, user)
        row = conn.execute("SELECT r.*, e.result_json, e.evidence_metadata_json FROM evaluation_runs r LEFT JOIN evaluation_results e ON e.run_id=r.id WHERE r.id=%s AND r.organization_id=%s", (run_id, organization_id)).fetchone()
        if row is None: return None
        keys = ["id","organization_id","project_id","idempotency_key","status","provider","sample_count","created_at","result_json","evidence_metadata_json"]
        return dict(zip(keys, tuple(row)))
