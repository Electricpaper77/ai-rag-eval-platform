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
def browser_environment():
    if not os.getenv("AGENTTRUST_POSTGRES_URL"):
        pytest.fail("Gate 23B requires disposable PostgreSQL; refusing to skip")
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
        "AGENTTRUST_PUBLIC_ORIGIN": "http://127.0.0.1:8766",
        "AGENTTRUST_TEST_HTTP_COOKIES": "true",
        "AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY": "{}",
    }.items():
        monkeypatch.setenv(key, value)
    migrate()
    monkeypatch.setattr(saas_repository, "connect", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SQLite accessed in Gate 23B")))
    monkeypatch.setattr(saas_router, "exchange_code", lambda config, code, verifier: code)
    monkeypatch.setattr(
        saas_router,
        "verify_id_token",
        lambda token, config, expected_nonce=None: {"issuer": config.issuer, "subject": f"{token}-user"},
    )
    from uvicorn import Config, Server
    server = Server(Config(app, host="127.0.0.1", port=8766, log_level="error"))
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
        pytest.fail("FastAPI Gate 23B server did not become healthy")

    def login_as(code):
        with TestClient(app, base_url="https://testserver") as client:
            login = client.get("/saas/auth/login", follow_redirects=False)
            state = login.json()["state"]
            callback = client.get(f"/saas/auth/callback?code={code}&state={state}")
            assert callback.status_code == 200, callback.text
            return {name: callback.cookies[name] for name in ("agenttrust_session", "agenttrust_csrf")}

    cookies_a = login_as("browser-23b-a")
    cookies_b = login_as("browser-23b-b")
    try:
        yield "http://127.0.0.1:8766/saas-workspace.html", cookies_a, cookies_b
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        monkeypatch.undo()


def _headers(cookies):
    return {"Origin": "http://127.0.0.1:8766", "X-CSRF-Token": cookies["agenttrust_csrf"]}


def test_authenticated_create_history_detail_compare_export_refresh_and_isolation(browser_environment):
    # Keep the general regression collection independent from the browser stack.
    # Gate 23B installs Playwright explicitly; when this postgres-marked module is
    # selected without that dependency, fail at execution rather than silently
    # skipping the mandatory browser journey.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        pytest.fail(f"Gate 23B requires Playwright; refusing to skip: {exc}")
    base_url, cookies_a, cookies_b = browser_environment
    evidence = {"schema": "gate23b-browser-v1", "synthetic_only": True, "steps": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        mobile = browser.new_context(viewport={"width": 390, "height": 844})
        mobile.add_cookies([{"name": k, "value": v, "url": base_url, "secure": False} for k, v in cookies_a.items()])
        page = mobile.new_page()
        page.goto(base_url)
        page.screenshot(path="artifacts/gate23b/workspace-mobile.png", full_page=True)
        page.get_by_text("No authorized organizations are available.").wait_for()
        api = page.request
        headers = _headers(cookies_a)
        organization = api.post("http://127.0.0.1:8766/saas/organizations", data={"name": "Tenant A"}, headers=headers)
        assert organization.status == 200
        org_a = organization.json()["id"]
        project = api.post("http://127.0.0.1:8766/saas/projects", data={"organization_id": org_a, "name": "<img src=x onerror=alert(1)>"}, headers=headers)
        assert project.status == 200
        project_a = project.json()["id"]
        run_ids = []
        for key in ("gate23b-a-1", "gate23b-a-2"):
            result = api.post(f"http://127.0.0.1:8766/saas/projects/{project_a}/evaluations", data='{"answer":"synthetic"}\n', headers={**headers, "X-Organization-Id": org_a, "Idempotency-Key": key})
            assert result.status == 200
            run_ids.append(result.json()["id"])
        evidence["steps"].append({"create": "passed", "persisted_runs": len(run_ids)})
        page.reload()
        page.get_by_label("Organization").select_option(org_a)
        page.get_by_label("Project").select_option(project_a)
        assert page.locator("img").count() == 0
        page.get_by_role("button", name="Evaluations").click()
        page.get_by_text(run_ids[0]).wait_for()
        detail = api.get(f"http://127.0.0.1:8766/saas/evaluations/{run_ids[0]}?organization_id={org_a}")
        assert detail.status == 200 and detail.json()["status"] == "completed"
        compare = api.get(f"http://127.0.0.1:8766/saas/evaluations/compare?organization_id={org_a}&run_id_a={run_ids[0]}&run_id_b={run_ids[1]}")
        assert compare.status == 200 and len(compare.json()["runs"]) == 2
        exported = api.get(f"http://127.0.0.1:8766/saas/evaluations/{run_ids[0]}/export?format=json&organization_id={org_a}")
        assert exported.status == 200 and 'attachment' in exported.headers.get("content-disposition", "")
        csv_export = api.get(f"http://127.0.0.1:8766/saas/evaluations/{run_ids[0]}/export?format=csv&organization_id={org_a}")
        assert csv_export.status == 200 and "content-disposition" in csv_export.headers
        with psycopg.connect(os.environ["AGENTTRUST_POSTGRES_URL"]) as conn:
            conn.execute("UPDATE evaluation_results SET result_json=%s WHERE run_id=%s", (json.dumps({"note": "=FORMULA"}), run_ids[0]))
            conn.commit()
        sanitized = api.get(f"http://127.0.0.1:8766/saas/evaluations/{run_ids[0]}/export?format=csv&organization_id={org_a}")
        assert "'=FORMULA" in sanitized.text
        page.reload()
        page.get_by_label("Organization").select_option(org_a)
        page.get_by_label("Project").select_option(project_a)
        page.get_by_role("button", name="Results").click()
        page.get_by_text("completed").wait_for()
        desktop = browser.new_context(viewport={"width": 1440, "height": 900})
        desktop.add_cookies([{"name": k, "value": v, "url": base_url, "secure": False} for k, v in cookies_a.items()])
        desktop_page = desktop.new_page(); desktop_page.goto(base_url); desktop_page.screenshot(path="artifacts/gate23b/workspace-desktop.png", full_page=True)
        evidence["steps"].extend([{"detail": "passed"}, {"compare": "passed"}, {"json_export": "passed"}, {"csv_formula_escape": "passed"}, {"mobile_refresh": "passed"}, {"desktop": "passed"}])
        desktop.close()
        mobile.close()
        browser.close()

    with TestClient(__import__("backend.app.main", fromlist=["app"]).app, base_url="http://127.0.0.1:8766") as client:
        org_b_response = client.post("/saas/organizations", json={"name": "Tenant B"}, headers=_headers(cookies_b), cookies=cookies_b)
        assert org_b_response.status_code == 200
        org_b = org_b_response.json()["id"]
        project_b_response = client.post("/saas/projects", json={"organization_id": org_b, "name": "B Project"}, headers=_headers(cookies_b), cookies=cookies_b)
        assert project_b_response.status_code == 200
        project_b = project_b_response.json()["id"]
        run_b = client.post(f"/saas/projects/{project_b}/evaluations", content='{"answer":"b"}\n', headers={**_headers(cookies_b), "X-Organization-Id": org_b, "Idempotency-Key": "gate23b-b-1"}, cookies=cookies_b)
        assert run_b.status_code == 200
        run_b_id = run_b.json()["id"]
        with TestClient(__import__("backend.app.main", fromlist=["app"]).app, base_url="http://127.0.0.1:8766") as denied:
            assert denied.get(f"/saas/evaluations?organization_id={org_b}", cookies=cookies_a).status_code == 403
            assert denied.get(f"/saas/evaluations/{run_b_id}?organization_id={org_b}", cookies=cookies_a).status_code == 403
            assert denied.get(f"/saas/evaluations/{run_b_id}/export?format=json&organization_id={org_b}", cookies=cookies_a).status_code == 403
        os.environ["AGENTTRUST_RESTORE_TARGET_DB"] = "gate23b-quarantined-target"
        try:
            with TestClient(__import__("backend.app.main", fromlist=["app"]).app, base_url="http://127.0.0.1:8766") as quarantined:
                assert quarantined.get("/saas/organizations", cookies=cookies_a).status_code == 503
        finally:
            os.environ.pop("AGENTTRUST_RESTORE_TARGET_DB", None)
    evidence["steps"].extend([{"cross_tenant_denial": "passed"}, {"quarantine_denial": "passed"}])
    Path("artifacts/gate23b").mkdir(parents=True, exist_ok=True)
    Path("artifacts/gate23b/results.json").write_text(json.dumps(evidence, sort_keys=True) + "\n", encoding="utf-8")

