"""Gate 21E: authenticated HTTP journey against disposable PostgreSQL."""
import os
import json
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
import saas.router as saas_router
from saas.postgres_repository import migrate, PostgresSessionStore, connect, hash_secret, bind_request_database, reset_request_database, user_id

pytestmark = pytest.mark.postgres_integration


def test_authenticated_customer_journey_uses_postgres(monkeypatch):
    if not os.getenv("AGENTTRUST_POSTGRES_URL"):
        pytest.fail("Gate 21E requires disposable PostgreSQL; refusing to skip")
    monkeypatch.delenv("AGENTTRUST_SAAS_DB", raising=False)
    migrate()
    monkeypatch.setenv("AGENTTRUST_DEPLOYMENT_POLICY", "production")
    monkeypatch.setenv("AGENTTRUST_MANAGED_DEPLOYMENT", "true")
    monkeypatch.setenv("AGENTTRUST_SHARED_SESSION_STORE", "postgres")
    monkeypatch.setenv("AGENTTRUST_OIDC_STATE_ENCRYPTION_KEY", "P7y3zWsvjYfZQTnBjqmAX8MhuXBOT3_5mBJRKeqQpI8=")
    monkeypatch.setenv("AGENTTRUST_SAAS_RUNTIME_MODE", "production")
    monkeypatch.setenv("AGENTTRUST_PUBLIC_ORIGIN", "https://testserver")
    for key, value in {
        "AGENTTRUST_OIDC_ISSUER":"https://issuer.example",
        "AGENTTRUST_OIDC_AUDIENCE":"agenttrust",
        "AGENTTRUST_OIDC_AUTHORIZATION_ENDPOINT":"https://issuer.example/authorize",
        "AGENTTRUST_OIDC_JWKS_URI":"https://issuer.example/jwks",
        "AGENTTRUST_OIDC_CLIENT_ID":"client",
        "AGENTTRUST_OIDC_REDIRECT_URI":"https://testserver/saas/auth/callback",
        "AGENTTRUST_OIDC_TOKEN_ENDPOINT":"https://issuer.example/token",
    }.items(): monkeypatch.setenv(key, value)
    monkeypatch.setattr(saas_router, "exchange_code", lambda config, code, verifier: "controlled-token")
    monkeypatch.setattr(saas_router, "verify_id_token", lambda token, config, expected_nonce=None: {"issuer": config.issuer, "subject": "customer-a", "email": "ignored"})
    client = TestClient(app, base_url="https://testserver")
    login = client.get("/saas/auth/login", follow_redirects=False)
    assert login.status_code == 307
    state = login.json()["state"]
    callback = client.get(f"/saas/auth/callback?code=one-time&state={state}")
    assert callback.status_code == 200 and callback.json()["authenticated"] is True
    csrf = callback.json()["csrf_token"]
    # Pin the callback-issued secure cookies into the HTTPS test client jar;
    # this keeps the assertion about the real Set-Cookie values deterministic.
    callback_cookie = f"agenttrust_session={callback.cookies['agenttrust_session']}; agenttrust_csrf={callback.cookies['agenttrust_csrf']}"
    headers = {"Origin":"https://testserver", "X-CSRF-Token":csrf, "Cookie":callback_cookie}
    assert client.post("/saas/organizations", json={"name":"missing-csrf"}, headers={"Cookie":callback_cookie,"Origin":"https://testserver"}).status_code == 403
    assert client.post("/saas/organizations", json={"name":"bad-origin"}, headers={**headers,"Origin":"https://evil.example"}).status_code == 403
    org_response = client.post("/saas/organizations", json={"name":"Customer A"}, headers=headers)
    assert org_response.status_code == 200, org_response.text
    org = org_response.json()
    project = client.post("/saas/projects", json={"organization_id":org["id"],"name":"Eval"}, headers=headers)
    assert project.status_code == 200
    assert client.post("/saas/projects", json={"organization_id":org["id"],"name":"bad"}, headers={"Cookie":callback_cookie,"Origin":"https://testserver"}).status_code == 403
    payload = "{\"prompt\":\"hello\"}\n"
    run = client.post(f"/saas/projects/{project.json()['id']}/evaluations", content=payload, headers={**headers,"X-Organization-Id":org["id"],"Idempotency-Key":"journey-1"})
    assert run.status_code == 200 and run.json()["provider"] == "mock"
    assert client.post(f"/saas/projects/{project.json()['id']}/evaluations", content=payload, headers={"Cookie":callback_cookie,"Origin":"https://testserver","X-Organization-Id":org["id"],"Idempotency-Key":"csrf-1"}).status_code == 403
    result = client.get(f"/saas/evaluations/{run.json()['id']}", headers={"X-Organization-Id":org["id"]})
    result_body = result.json()
    result_json = json.loads(result_body["result_json"]) if isinstance(result_body["result_json"], str) else result_body["result_json"]
    assert result.status_code == 200 and result_json["provider"] == "mock"
    assert client.post("/saas/organizations", json={"name":"blocked"}).status_code == 403
    logout = client.post("/saas/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert 'agenttrust_csrf=""' in logout.headers.get("set-cookie", "")
    assert client.get(f"/saas/evaluations/{run.json()['id']}", headers={"X-Organization-Id":org["id"]}).status_code == 401
    with connect() as conn:
        assert conn.execute("SELECT 1 FROM organizations WHERE id=%s", (org["id"],)).fetchone()
        assert conn.execute("SELECT 1 FROM projects WHERE id=%s", (project.json()["id"],)).fetchone()
        assert conn.execute("SELECT 1 FROM evaluation_runs WHERE id=%s", (run.json()["id"],)).fetchone()
    sqlite_path = os.getenv("AGENTTRUST_SAAS_DB", "")
    assert not sqlite_path or not os.path.exists(sqlite_path)

@pytest.mark.postgres_integration
def test_two_independent_postgres_session_stores_expiry_and_revocation(monkeypatch):
    if not os.getenv("AGENTTRUST_POSTGRES_URL"):
        pytest.fail("Gate 21I requires disposable PostgreSQL; refusing to skip")
    monkeypatch.delenv("AGENTTRUST_SAAS_DB", raising=False); migrate()
    first, second = PostgresSessionStore(connect), PostgresSessionStore(connect)
    import secrets, time
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    user = {"issuer":"https://issuer.example", "subject":"two-instance"}
    first.put(sid, user, time.time()+60, csrf)
    assert second.get(sid, csrf)["subject"] == "two-instance"
    first.revoke(sid); assert second.get(sid, csrf) is None
    sid2 = secrets.token_urlsafe(32); first.put(sid2, user, time.time()-1, csrf)
    assert second.get(sid2, csrf) is None
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE session_hash=%s", (hash_secret(sid),)).fetchone()[0] == 1

def test_authenticated_http_rejects_quarantined_postgres_target(monkeypatch):
    if not os.getenv("AGENTTRUST_POSTGRES_URL"): pytest.fail("Gate 22D requires disposable PostgreSQL; refusing to skip")
    monkeypatch.delenv("AGENTTRUST_SAAS_DB", raising=False); monkeypatch.setenv("AGENTTRUST_RESTORE_TARGET_DB", "quarantine-target")
    monkeypatch.setenv("AGENTTRUST_SAAS_RUNTIME_MODE", "production")
    monkeypatch.setenv("AGENTTRUST_DEPLOYMENT_POLICY", "production"); monkeypatch.setenv("AGENTTRUST_MANAGED_DEPLOYMENT", "true"); monkeypatch.setenv("AGENTTRUST_SHARED_SESSION_STORE", "postgres"); monkeypatch.setenv("AGENTTRUST_OIDC_STATE_ENCRYPTION_KEY", "P7y3zWsvjYfZQTnBjqmAX8MhuXBOT3_5mBJRKeqQpI8=")
    monkeypatch.setattr(saas_router, "verify_id_token", lambda token, config, expected_nonce=None: {"issuer": config.issuer, "subject": "quarantine-http"})
    for key, value in {"AGENTTRUST_OIDC_ISSUER":"https://issuer.example","AGENTTRUST_OIDC_AUDIENCE":"agenttrust","AGENTTRUST_OIDC_JWKS_URI":"https://issuer.example/jwks","AGENTTRUST_OIDC_CLIENT_ID":"client","AGENTTRUST_OIDC_REDIRECT_URI":"https://testserver/saas/auth/callback","AGENTTRUST_OIDC_TOKEN_ENDPOINT":"https://issuer.example/token","AGENTTRUST_OIDC_AUTHORIZATION_ENDPOINT":"https://issuer.example/authorize"}.items(): monkeypatch.setenv(key, value)
    response = TestClient(app, base_url="https://testserver").post("/saas/organizations", json={"name":"blocked"}, headers={"Authorization":"Bearer synthetic"})
    assert response.status_code == 503

def test_two_target_fastapi_http_quarantine_promotion_and_tenant_isolation(monkeypatch, tmp_path):
    """Real HTTP requests use two isolated PostgreSQL targets and the trusted promotion gate."""
    if not os.getenv("AGENTTRUST_POSTGRES_URL"): pytest.fail("Gate 22D.8 requires disposable PostgreSQL; refusing to skip")
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from fastapi import FastAPI, Request
    from saas.lifecycle import DeletionJournal, reconcile_restored_tenant, restore_access_allowed
    from saas.recovery import RecoveryOrchestrator, write_approval
    base = conninfo_to_dict(os.environ["AGENTTRUST_POSTGRES_URL"])
    admin = dict(base, dbname="postgres")
    suffix = __import__("uuid").uuid4().hex[:8]
    targets = {"target_a_" + suffix, "target_b_" + suffix}
    urls = {name: make_conninfo(**dict(base, dbname=name)) for name in targets}
    with psycopg.connect(make_conninfo(**admin), autocommit=True) as conn:
        for name in targets: conn.execute(f'CREATE DATABASE "{name}"')
    try:
        original_url = os.environ["AGENTTRUST_POSTGRES_URL"]
        for name in targets:
            monkeypatch.setenv("AGENTTRUST_POSTGRES_URL", urls[name]); migrate()
            with connect() as conn:
                with conn.transaction():
                    uid = "https://issuer.example|two-target-user"
                    conn.execute("INSERT INTO users(id,issuer,subject,created_at) VALUES (%s,%s,%s,now()) ON CONFLICT (id) DO NOTHING", (uid, "https://issuer.example", "two-target-user"))
                    conn.execute("INSERT INTO organizations(id,name,created_at) VALUES (%s,%s,now())", (f"seed_{name}", name))
                    conn.execute("INSERT INTO memberships(organization_id,user_id,role,active,created_at) VALUES (%s,%s,'owner',TRUE,now())", (f"seed_{name}", uid))
        monkeypatch.setenv("AGENTTRUST_POSTGRES_URL", original_url)
        journal = DeletionJournal(tmp_path / "two-target-journal.jsonl")
        event = journal.append("seed_" + next(iter(targets)), "two-target-user")
        monkeypatch.setenv("AGENTTRUST_RECOVERY_APPROVAL_KEY", "t" * 32)
        monkeypatch.setenv("AGENTTRUST_RECOVERY_APPROVERS", "two-target-operator")
        promoted = next(iter(targets)); promoted_url = urls[promoted]
        monkeypatch.setenv("AGENTTRUST_POSTGRES_URL", promoted_url)
        with psycopg.connect(promoted_url) as conn:
            conn.execute("INSERT INTO tenant_restore_reconciliation(organization_id,journal_digest,reconciled_at) VALUES (%s,%s,now())", ("seed_" + promoted, event["digest"]))
            conn.commit()
            approval = tmp_path / "approval.json"
            write_approval(approval, "backup-two-target", event["digest"], "two-target-operator", target_database=promoted)
            assert RecoveryOrchestrator(conn, journal, approval, promoted).promote("seed_" + promoted, "backup-two-target", event["digest"])["promoted"]
            assert restore_access_allowed(conn, "seed_" + promoted)
        monkeypatch.setenv("AGENTTRUST_DEPLOYMENT_POLICY", "production"); monkeypatch.setenv("AGENTTRUST_MANAGED_DEPLOYMENT", "true"); monkeypatch.setenv("AGENTTRUST_SHARED_SESSION_STORE", "postgres"); monkeypatch.setenv("AGENTTRUST_OIDC_STATE_ENCRYPTION_KEY", "P7y3zWsvjYfZQTnBjqmAX8MhuXBOT3_5mBJRKeqQpI8="); monkeypatch.setenv("AGENTTRUST_SAAS_RUNTIME_MODE", "production"); monkeypatch.setenv("AGENTTRUST_PUBLIC_ORIGIN", "https://testserver")
        for key, value in {"AGENTTRUST_OIDC_ISSUER":"https://issuer.example","AGENTTRUST_OIDC_AUDIENCE":"agenttrust","AGENTTRUST_OIDC_AUTHORIZATION_ENDPOINT":"https://issuer.example/authorize","AGENTTRUST_OIDC_JWKS_URI":"https://issuer.example/jwks","AGENTTRUST_OIDC_CLIENT_ID":"client","AGENTTRUST_OIDC_REDIRECT_URI":"https://testserver/saas/auth/callback","AGENTTRUST_OIDC_TOKEN_ENDPOINT":"https://issuer.example/token"}.items(): monkeypatch.setenv(key, value)
        monkeypatch.setattr(saas_router, "verify_id_token", lambda token, config, expected_nonce=None: {"issuer": config.issuer, "subject": "two-target-user"})
        def make_target_app(target):
            instance = FastAPI()
            @instance.middleware("http")
            async def bind_target(request: Request, call_next):
                token = bind_request_database(target)
                try: return await call_next(request)
                finally: reset_request_database(token)
            instance.include_router(saas_router.router)
            return instance
        def request(target, method, path, **kwargs):
            with TestClient(make_target_app(target), base_url="https://testserver") as client:
                return getattr(client, method)(path, **kwargs)
        blocked = next(name for name in targets if name != promoted)
        headers = {"Authorization":"Bearer controlled"}
        assert request(blocked, "post", "/saas/organizations", json={"name":"blocked"}, headers=headers).status_code == 503
        org = request(promoted, "post", "/saas/organizations", json={"name":"Promoted Tenant"}, headers=headers)
        assert org.status_code == 200, org.text
        org_id = org.json()["id"]
        project = request(promoted, "post", "/saas/projects", json={"organization_id":org_id,"name":"Project"}, headers=headers)
        assert project.status_code == 200
        run = request(promoted, "post", f"/saas/projects/{project.json()['id']}/evaluations", content='{"prompt":"synthetic"}\n', headers={**headers,"X-Organization-Id":org_id,"Idempotency-Key":"two-target-1"})
        assert run.status_code == 200 and run.json()["provider"] == "mock"
        result = request(promoted, "get", f"/saas/evaluations/{run.json()['id']}", headers={**headers,"X-Organization-Id":org_id})
        assert result.status_code == 200
        assert request(promoted, "post", "/saas/projects", json={"organization_id":"seed_other","name":"cross"}, headers=headers).status_code == 403
        assert request(blocked, "post", "/saas/organizations", json={"name":"still blocked"}, headers=headers).status_code == 503
    finally:
        with psycopg.connect(make_conninfo(**admin), autocommit=True) as conn:
            for name in targets: conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
