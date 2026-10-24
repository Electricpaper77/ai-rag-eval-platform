import hashlib
import json
import os
import threading
import time
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.postgres_integration


@pytest.fixture(scope="module")
def investigation_environment():
    if not os.getenv("AGENTTRUST_POSTGRES_URL"):
        pytest.fail("Gate 23D requires disposable PostgreSQL; refusing to skip")
    import saas.repository as saas_repository
    import saas.router as saas_router
    from saas.postgres_repository import migrate
    from backend.app.main import app

    monkeypatch = pytest.MonkeyPatch()
    values = {
        "AGENTTRUST_SAAS_DB": "",
        "AGENTTRUST_SAAS_BACKEND": "postgres",
        "AGENTTRUST_SAAS_RUNTIME_MODE": "test",
        "AGENTTRUST_DEPLOYMENT_POLICY": "test",
        "AGENTTRUST_OIDC_ISSUER": "https://issuer.example",
        "AGENTTRUST_OIDC_AUDIENCE": "agenttrust",
        "AGENTTRUST_OIDC_CLIENT_ID": "client",
        "AGENTTRUST_OIDC_REDIRECT_URI": "https://testserver/saas/auth/callback",
        "AGENTTRUST_OIDC_AUTHORIZATION_ENDPOINT": "https://issuer.example/authorize",
        "AGENTTRUST_OIDC_TOKEN_ENDPOINT": "https://issuer.example/token",
        "AGENTTRUST_OIDC_JWKS_URI": "https://issuer.example/jwks",
        "AGENTTRUST_PUBLIC_ORIGIN": "http://127.0.0.1:8768",
        "AGENTTRUST_TEST_HTTP_COOKIES": "true",
        "AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY": "{}",
    }
    for key, value in values.items(): monkeypatch.setenv(key, value)
    migrate()
    monkeypatch.setattr(saas_repository, "connect", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SQLite accessed in Gate 23D")))
    monkeypatch.setattr(saas_router, "exchange_code", lambda config, code, verifier: code)
    monkeypatch.setattr(saas_router, "verify_id_token", lambda token, config, expected_nonce=None: {"issuer": config.issuer, "subject": f"{token}-user"})
    from uvicorn import Config, Server
    server = Server(Config(app, host="127.0.0.1", port=8768, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with TestClient(app, base_url="https://testserver") as probe:
                if probe.get("/health").status_code == 200: break
        except Exception: pass
        time.sleep(0.2)
    else: pytest.fail("FastAPI Gate 23D server did not become healthy")

    def login_as(code):
        with TestClient(app, base_url="https://testserver") as client:
            login = client.get("/saas/auth/login", follow_redirects=False); state = login.json()["state"]
            callback = client.get(f"/saas/auth/callback?code={code}&state={state}")
            assert callback.status_code == 200, callback.text
            return {name: callback.cookies[name] for name in ("agenttrust_session", "agenttrust_csrf")}

    try:
        yield "http://127.0.0.1:8768/saas-workspace.html", login_as("gate23d-a"), login_as("gate23d-b")
    finally:
        server.should_exit = True; thread.join(timeout=5); monkeypatch.undo()


def _headers(cookies):
    return {"Origin": "http://127.0.0.1:8768", "X-CSRF-Token": cookies["agenttrust_csrf"]}


def test_real_case_investigation_annotation_release_review_export_and_chromium(investigation_environment):
    base_url, cookies_a, cookies_b = investigation_environment
    origin = base_url.split("/saas-workspace.html", 1)[0]
    from backend.app.main import app
    headers = _headers(cookies_a)
    with TestClient(app, base_url=origin) as client:
        org = client.post("/saas/organizations", json={"name": "Gate 23D Tenant A"}, headers=headers, cookies=cookies_a); assert org.status_code == 200, org.text
        org_id = org.json()["id"]
        project = client.post("/saas/projects", json={"organization_id": org_id, "name": "Investigation project"}, headers=headers, cookies=cookies_a); assert project.status_code == 200, project.text
        project_id = project.json()["id"]
        headers_b = _headers(cookies_b)
        org_b = client.post("/saas/organizations", json={"name": "Gate 23D Tenant B"}, headers=headers_b, cookies=cookies_b); assert org_b.status_code == 200, org_b.text
        org_b_id = org_b.json()["id"]
        project_b = client.post("/saas/projects", json={"organization_id": org_b_id, "name": "Tenant B project"}, headers=headers_b, cookies=cookies_b); assert project_b.status_code == 200, project_b.text
        project_b_id = project_b.json()["id"]
        run = client.post(f"/saas/projects/{project_id}/evaluations", content='{"prompt":"synthetic failed case"}\n', headers={**headers, "X-Organization-Id": org_id, "Idempotency-Key": "gate23d-run"}, cookies=cookies_a); assert run.status_code == 200, run.text
        run_id = run.json()["id"]
        policy = client.post("/saas/policies", json={"organization_id": org_id, "project_id": project_id, "name": "investigation-policy", "metrics": {"quality": {"direction": "higher_is_better", "threshold": 0.8, "accepted_provenance": ["synthetic_test"]}}, "require_baseline": False}, headers=headers, cookies=cookies_a); assert policy.status_code == 200, policy.text
        decision = client.post(f"/saas/evaluations/{run_id}/decision?organization_id={org_id}", json={"policy_id": policy.json()["id"], "idempotency_key": "gate23d-decision"}, headers=headers, cookies=cookies_a); assert decision.status_code == 200, decision.text
        with psycopg.connect(os.environ["AGENTTRUST_POSTGRES_URL"]) as conn:
            evidence = {"source": "synthetic_test_case", "citation": "fixture-only"}; digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            conn.execute("INSERT INTO evaluation_cases VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", ("case_gate23d", org_id, project_id, run_id, "case-1", "failed", "groundedness", 0.1, json.dumps(evidence), digest, "synthetic_test", "2026-01-01T00:00:00+00:00")); conn.commit()
        cases = client.get(f"/saas/evaluations/{run_id}/cases?organization_id={org_id}&project_id={project_id}", cookies=cookies_a); assert cases.status_code == 200 and cases.json()["evidence_status"] == "AVAILABLE" and cases.json()["cases"][0]["provenance"] == "synthetic_test"
        review = client.post(f"/saas/cases/case_gate23d/reviews?organization_id={org_id}", json={"status":"confirmed","comment":"Persisted synthetic case reviewed.","expected_revision":0,"idempotency_key":"gate23d-review"}, headers=headers, cookies=cookies_a); assert review.status_code == 200 and review.json()["provenance"] == "reviewer_confirmed"
        replay = client.post(f"/saas/cases/case_gate23d/reviews?organization_id={org_id}", json={"status":"hold","comment":"replay","expected_revision":0,"idempotency_key":"gate23d-review"}, headers=headers, cookies=cookies_a); assert replay.status_code == 200 and replay.json()["id"] == review.json()["id"]
        stale = client.post(f"/saas/cases/case_gate23d/reviews?organization_id={org_id}", json={"status":"hold","comment":"stale","expected_revision":0,"idempotency_key":"gate23d-stale"}, headers=headers, cookies=cookies_a); assert stale.status_code == 409
        release = client.post(f"/saas/release-reviews?organization_id={org_id}", json={"project_id":project_id,"decision_id":decision.json()["id"],"recommendation":"hold","idempotency_key":"gate23d-release"}, headers=headers, cookies=cookies_a); assert release.status_code == 200 and release.json()["decision_status"] in {"PASS","HOLD","INSUFFICIENT_EVIDENCE"}
        exported = client.get(f"/saas/release-reviews/{release.json()['id']}/export?organization_id={org_id}&format=json", cookies=cookies_a); assert exported.status_code == 200 and "non_production_disclaimer" in exported.json()
        cross = client.get(f"/saas/evaluations/{run_id}/cases?organization_id={org_b_id}&project_id={project_b_id}", cookies=cookies_b); assert cross.status_code == 404
        cross_export = client.get(f"/saas/release-reviews/{release.json()['id']}/export?organization_id={org_b_id}&format=json", cookies=cookies_b); assert cross_export.status_code == 404
        missing = client.get(f"/saas/evaluations/{run_id}/cases?organization_id={org_id}&project_id={project_id}&page_size=1000", cookies=cookies_a); assert missing.status_code == 200 and missing.json()["page_size"] == 100
        Path("artifacts/gate23d").mkdir(parents=True, exist_ok=True)
        Path("artifacts/gate23d/results.json").write_text(json.dumps({"schema":"gate23d-evidence-v1","synthetic_only":True,"steps":["authenticated_case_listing","reviewer_annotation","release_review","sanitized_export","cross_tenant_denial"],"run_id":run_id,"case_id":"case_gate23d","release_review_id":release.json()["id"]}, sort_keys=True, indent=2)+"\n", encoding="utf-8")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True); context = browser.new_context()
            context.add_cookies([{"name": name, "value": value, "url": origin} for name, value in cookies_a.items()])
            page = context.new_page(); page.goto(base_url); page.wait_for_selector('select[aria-label="Organization"] option:not([disabled])', state="attached", timeout=15000)
            page.get_by_role("button", name="Evaluations").click(); page.get_by_text(run_id).wait_for(timeout=15000); page.get_by_role("button", name="Inspect result").first.click()
            page.get_by_role("button", name="Investigation").click(); page.get_by_role("button", name="Load persisted cases").click(); page.get_by_text("case-1").wait_for(timeout=15000); assert "Persisted case evidence" in page.locator("#content").inner_text()
            page.screenshot(path="artifacts/gate23d/investigation-desktop.png", full_page=True)
            page.screenshot(path="artifacts/gate23d/investigation-mobile.png", full_page=True)
            browser.close()

