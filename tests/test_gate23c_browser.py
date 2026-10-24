import json
import os
import threading
import time
from urllib.parse import urlsplit
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.postgres_integration


@pytest.fixture(scope="module")
def decision_environment():
    if not os.getenv("AGENTTRUST_POSTGRES_URL"):
        pytest.fail("Gate 23C requires disposable PostgreSQL; refusing to skip")
    import saas.repository as saas_repository
    import saas.router as saas_router
    from saas.postgres_repository import migrate
    from backend.app.main import app

    monkeypatch = pytest.MonkeyPatch()
    for key, value in {
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
        "AGENTTRUST_PUBLIC_ORIGIN": "http://127.0.0.1:8767",
        "AGENTTRUST_TEST_HTTP_COOKIES": "true",
        "AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY": "{}",
    }.items():
        monkeypatch.setenv(key, value)
    migrate()
    monkeypatch.setattr(saas_repository, "connect", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SQLite accessed in Gate 23C")))
    monkeypatch.setattr(saas_router, "exchange_code", lambda config, code, verifier: code)
    monkeypatch.setattr(saas_router, "verify_id_token", lambda token, config, expected_nonce=None: {"issuer": config.issuer, "subject": f"{token}-user"})
    from uvicorn import Config, Server
    server = Server(Config(app, host="127.0.0.1", port=8767, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with TestClient(app, base_url="https://testserver") as probe:
                if probe.get("/health").status_code == 200:
                    break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        pytest.fail("FastAPI Gate 23C server did not become healthy")

    def login_as(code):
        with TestClient(app, base_url="https://testserver") as client:
            login = client.get("/saas/auth/login", follow_redirects=False)
            state = login.json()["state"]
            callback = client.get(f"/saas/auth/callback?code={code}&state={state}")
            assert callback.status_code == 200, callback.text
            return {name: callback.cookies[name] for name in ("agenttrust_session", "agenttrust_csrf")}

    try:
        yield "http://127.0.0.1:8767/saas-workspace.html", login_as("gate23c-a"), login_as("gate23c-b")
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        monkeypatch.undo()


def _headers(cookies):
    return {"Origin": "http://127.0.0.1:8767", "X-CSRF-Token": cookies["agenttrust_csrf"]}


def test_authenticated_scorecard_pass_hold_history_export_and_isolation(decision_environment):
    base_url, cookies_a, cookies_b = decision_environment
    origin = base_url.split("/saas-workspace.html", 1)[0]
    evidence = {"schema": "gate23c-browser-v1", "synthetic_only": True, "steps": []}
    from playwright.sync_api import sync_playwright

    with TestClient(__import__("backend.app.main", fromlist=["app"]).app, base_url=origin) as client:
        headers = _headers(cookies_a)
        org = client.post("/saas/organizations", json={"name": "Decision Tenant A"}, headers=headers, cookies=cookies_a)
        assert org.status_code == 200
        org_id = org.json()["id"]
        project = client.post("/saas/projects", json={"organization_id": org_id, "name": "Reliability Project"}, headers=headers, cookies=cookies_a)
        assert project.status_code == 200
        project_id = project.json()["id"]
        def run(key, value):
            return client.post(f"/saas/projects/{project_id}/evaluations", content=json.dumps({"recorded_metrics": {"quality": value}}) + "\n", headers={**headers, "X-Organization-Id": org_id, "Idempotency-Key": key}, cookies=cookies_a)
        baseline = run("gate23c-baseline", 0.85).json()["id"]
        passing = run("gate23c-pass", 0.90).json()["id"]
        regressed = run("gate23c-hold", 0.70).json()["id"]
        policy = client.post("/saas/policies", json={"organization_id": org_id, "project_id": project_id, "name": "quality-gate", "metrics": {"quality": {"direction": "higher_is_better", "threshold": 0.8, "tolerance": 0.05, "unit": "score", "accepted_provenance": ["synthetic_test"]}}, "require_baseline": True}, headers=headers, cookies=cookies_a)
        assert policy.status_code == 200, policy.text
        policy_id = policy.json()["id"]
        first = client.post(f"/saas/evaluations/{passing}/decision?organization_id={org_id}", json={"policy_id": policy_id, "baseline_run_id": baseline, "idempotency_key": "gate23c-decision-pass"}, headers=headers, cookies=cookies_a)
        assert first.status_code == 200 and first.json()["decision"] == "PASS"
        second = client.post(f"/saas/evaluations/{regressed}/decision?organization_id={org_id}", json={"policy_id": policy_id, "baseline_run_id": baseline, "idempotency_key": "gate23c-decision-hold"}, headers=headers, cookies=cookies_a)
        assert second.status_code == 200 and second.json()["decision"] == "HOLD"
        missing_policy = client.post("/saas/policies", json={"organization_id": org_id, "project_id": project_id, "name": "missing-evidence", "metrics": {"groundedness": {"direction": "higher_is_better", "threshold": 0.8, "unit": "score", "accepted_provenance": ["synthetic_test"]}}, "require_baseline": False}, headers=headers, cookies=cookies_a)
        assert missing_policy.status_code == 200, missing_policy.text
        insufficient = client.post(f"/saas/evaluations/{passing}/decision?organization_id={org_id}", json={"policy_id": missing_policy.json()["id"], "idempotency_key": "gate23c-decision-insufficient"}, headers=headers, cookies=cookies_a)
        assert insufficient.status_code == 200 and insufficient.json()["decision"] == "INSUFFICIENT_EVIDENCE"
        decisions = client.get(f"/saas/decisions?organization_id={org_id}&project_id={project_id}", cookies=cookies_a)
        assert decisions.status_code == 200 and decisions.json()["total"] == 3
        exported = client.get(f"/saas/decisions/{first.json()['id']}/export?organization_id={org_id}", cookies=cookies_a)
        assert exported.status_code == 200 and "attachment" in exported.headers.get("content-disposition", "")
        evidence["steps"].extend([{ "baseline_current": "passed" }, {"pass_decision": "passed"}, {"hold_decision": "passed"}, {"history": "passed"}, {"report_export": "passed"}])
        org_b = client.post("/saas/organizations", json={"name": "Decision Tenant B"}, headers=_headers(cookies_b), cookies=cookies_b)
        assert org_b.status_code == 200
        org_b_id = org_b.json()["id"]
        denied = client.get(f"/saas/decisions?organization_id={org_b_id}", cookies=cookies_a)
        assert denied.status_code == 403
        cross = client.get(f"/saas/decisions/{first.json()['id']}?organization_id={org_b_id}", cookies=cookies_a)
        assert cross.status_code == 403 or cross.status_code == 404
        evidence["steps"].append({"cross_tenant_denial": "passed"})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_cookies([{"name": k, "value": v, "url": base_url, "secure": False} for k, v in cookies_a.items()])
        page = context.new_page()
        browser_trace = []
        page.on("request", lambda request: browser_trace.append({"kind": "request", "url": urlsplit(request.url).path + ("?" + urlsplit(request.url).query if urlsplit(request.url).query else "")} ) if "/saas/decisions" in request.url else None)
        page.on("response", lambda response: browser_trace.append({"kind": "response", "url": urlsplit(response.url).path + ("?" + urlsplit(response.url).query if urlsplit(response.url).query else ""), "status": response.status, "total": response.json().get("total"), "count": len(response.json().get("decisions", []))}) if "/saas/decisions" in response.url and response.ok else None)
        page.goto(base_url)
        page.wait_for_function("() => Boolean(document.querySelector('[aria-label=Organization]')?.value && document.querySelector('[aria-label=Project]')?.value)")
        page.get_by_label("Organization").select_option(org_id)
        page.wait_for_function("() => Boolean(document.querySelector('[aria-label=Project]')?.value)")
        page.get_by_label("Project").select_option(project_id)
        browser_decisions = page.request.get(f"{origin}/saas/decisions?organization_id={org_id}&project_id={project_id}")
        assert browser_decisions.status == 200 and browser_decisions.json()["total"] == 3
        page.get_by_role("button", name="Scorecards").click()
        scorecard_id = page.get_by_text(first.json()["id"])
        try:
            scorecard_id.wait_for(timeout=10000)
        except Exception as exc:
            raise AssertionError(f"scorecard did not render at {page.url}: {page.locator('#content').inner_text()} trace={browser_trace}") from exc
        assert page.get_by_text("PASS").count() >= 1 and page.get_by_text("HOLD").count() >= 1
        page.screenshot(path="artifacts/gate23c/scorecards-mobile.png", full_page=True)
        page.reload(); page.wait_for_function("() => Boolean(document.querySelector('[aria-label=Organization]')?.value && document.querySelector('[aria-label=Project]')?.value)"); page.get_by_label("Organization").select_option(org_id); page.wait_for_function("() => Boolean(document.querySelector('[aria-label=Project]')?.value)"); page.get_by_label("Project").select_option(project_id); page.get_by_role("button", name="Scorecards").click(); assert page.get_by_text("INSUFFICIENT_EVIDENCE").count() >= 1
        context.close(); browser.close()
    os.environ["AGENTTRUST_RESTORE_TARGET_DB"] = "gate23c-quarantined-target"
    try:
        with TestClient(__import__("backend.app.main", fromlist=["app"]).app, base_url=origin) as quarantined:
            assert quarantined.get(f"/saas/decisions?organization_id={org_id}", cookies=cookies_a).status_code == 503
    finally:
        os.environ.pop("AGENTTRUST_RESTORE_TARGET_DB", None)
    evidence["steps"].append({"browser_refresh": "passed"})
    evidence["steps"].append({"quarantine_denial": "passed"})
    Path("artifacts/gate23c").mkdir(parents=True, exist_ok=True)
    Path("artifacts/gate23c/results.json").write_text(json.dumps(evidence, sort_keys=True) + "\n", encoding="utf-8")
