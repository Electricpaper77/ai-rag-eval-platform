"""Gate 21E: authenticated HTTP journey against disposable PostgreSQL."""
import os
import json
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
import saas.router as saas_router
from saas.postgres_repository import migrate

pytestmark = pytest.mark.postgres_integration


def test_authenticated_customer_journey_uses_postgres(monkeypatch):
    if not os.getenv("AGENTTRUST_POSTGRES_URL"):
        pytest.fail("Gate 21E requires disposable PostgreSQL; refusing to skip")
    monkeypatch.delenv("AGENTTRUST_SAAS_DB", raising=False)
    migrate()
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
    org_response = client.post("/saas/organizations", json={"name":"Customer A"}, headers=headers)
    assert org_response.status_code == 200, org_response.text
    org = org_response.json()
    project = client.post("/saas/projects", json={"organization_id":org["id"],"name":"Eval"}, headers=headers)
    assert project.status_code == 200
    payload = "{\"prompt\":\"hello\"}\n"
    run = client.post(f"/saas/projects/{project.json()['id']}/evaluations", content=payload, headers={**headers,"X-Organization-Id":org["id"],"Idempotency-Key":"journey-1"})
    assert run.status_code == 200 and run.json()["provider"] == "mock"
    result = client.get(f"/saas/evaluations/{run.json()['id']}", headers={"X-Organization-Id":org["id"]})
    result_body = result.json()
    result_json = json.loads(result_body["result_json"]) if isinstance(result_body["result_json"], str) else result_body["result_json"]
    assert result.status_code == 200 and result_json["provider"] == "mock"
    assert client.post("/saas/organizations", json={"name":"blocked"}).status_code == 403
    assert client.post("/saas/auth/logout", headers=headers).status_code == 200
    assert client.get(f"/saas/evaluations/{run.json()['id']}", headers={"X-Organization-Id":org["id"]}).status_code == 401
