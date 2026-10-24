"""Gate 21E: authenticated HTTP journey against disposable PostgreSQL."""
import os
import json
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
import saas.router as saas_router
from saas.postgres_repository import migrate, PostgresSessionStore, connect, hash_secret

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
