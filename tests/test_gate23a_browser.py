import os
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.postgres_integration
playwright = pytest.importorskip("playwright.sync_api")

@pytest.fixture(scope="module")
def browser_url():
    monkeypatch = pytest.MonkeyPatch()
    if not os.getenv("AGENTTRUST_POSTGRES_URL"):
        pytest.fail("Gate 23A browser acceptance requires disposable PostgreSQL; refusing to skip")
    import saas.router as saas_router
    import saas.repository as saas_repository
    from saas.postgres_repository import migrate
    from backend.app.main import app
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", "")
    monkeypatch.setenv("AGENTTRUST_SAAS_BACKEND", "postgres")
    monkeypatch.setenv("AGENTTRUST_SAAS_RUNTIME_MODE", "test")
    monkeypatch.setenv("AGENTTRUST_DEPLOYMENT_POLICY", "test")
    monkeypatch.setenv("AGENTTRUST_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("AGENTTRUST_OIDC_AUDIENCE", "agenttrust")
    monkeypatch.setenv("AGENTTRUST_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("AGENTTRUST_OIDC_REDIRECT_URI", "https://testserver/saas/auth/callback")
    monkeypatch.setenv("AGENTTRUST_OIDC_AUTHORIZATION_ENDPOINT", "https://issuer.example/authorize")
    monkeypatch.setenv("AGENTTRUST_OIDC_TOKEN_ENDPOINT", "https://issuer.example/token")
    monkeypatch.setenv("AGENTTRUST_OIDC_JWKS_URI", "https://issuer.example/jwks")
    monkeypatch.setenv("AGENTTRUST_PUBLIC_ORIGIN", "http://127.0.0.1:8765")
    monkeypatch.setenv("AGENTTRUST_TEST_HTTP_COOKIES", "true")
    monkeypatch.setenv("AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY", "{}")
    migrate()
    def sqlite_must_not_be_used(*args, **kwargs):
        raise AssertionError("SQLite connection opened during PostgreSQL browser acceptance")
    monkeypatch.setattr(saas_repository, "connect", sqlite_must_not_be_used)
    monkeypatch.setattr(saas_router, "exchange_code", lambda config, code, verifier: "controlled-token")
    monkeypatch.setattr(saas_router, "verify_id_token", lambda token, config, expected_nonce=None: {"issuer": config.issuer, "subject": "browser-user"})
    from uvicorn import Config, Server
    server = Server(Config(app, host="127.0.0.1", port=8765, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with TestClient(app, base_url="https://testserver") as probe:
                if probe.get("/health").status_code == 200: break
        except Exception: pass
        time.sleep(.2)
    else: pytest.fail("FastAPI browser server did not become healthy")
    with TestClient(app, base_url="https://testserver") as callback_client:
        login = callback_client.get("/saas/auth/login", follow_redirects=False)
        state = login.json()["state"]
        callback = callback_client.get(f"/saas/auth/callback?code=browser&state={state}")
        assert callback.status_code == 200, callback.text
        cookies = {name: callback.cookies[name] for name in ("agenttrust_session", "agenttrust_csrf")}
    yield "http://127.0.0.1:8765/saas-workspace.html", cookies
    server.should_exit = True
    thread.join(timeout=5)
    monkeypatch.undo()

def test_authenticated_workspace_browser_journey(browser_url, tmp_path):
    base_url, cookies = browser_url
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_cookies([{"name": name, "value": value, "url": base_url, "secure": False} for name, value in cookies.items()])
        page = context.new_page()
        page.goto(base_url)
        page.screenshot(path="artifacts/gate23a/workspace-mobile.png", full_page=True)
        page.get_by_text("No authorized organizations are available.").wait_for()
        csrf = cookies["agenttrust_csrf"]
        headers = {"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": csrf}
        api_base = "http://127.0.0.1:8765"
        org = page.request.post(api_base + "/saas/organizations", data={"name":"Browser Tenant"}, headers=headers)
        assert org.ok, org.text()
        organization = org.json()
        from saas.postgres_repository import connect
        with connect() as db:
            assert db.execute("SELECT 1 FROM organizations WHERE id=%s", (organization["id"],)).fetchone()
        project = page.request.post(api_base + "/saas/projects", data={"organization_id":organization["id"],"name":"Browser Project"}, headers=headers)
        assert project.ok, project.text()
        page.reload(); page.get_by_label("Organization").select_option(organization["id"])
        page.get_by_label("Project").select_option(project.json()["id"])
        page.get_by_role("button", name="Evaluations").click()
        page.get_by_role("button", name="Submit synthetic evaluation").click()
        page.get_by_text("Persisted run").wait_for()
        page.reload(); page.get_by_role("button", name="Results").click()
        page.get_by_text("completed").wait_for()
        browser.close()

def test_browser_contract_is_api_backed_and_safe():
    html = Path("frontend/saas-workspace.html").read_text(encoding="utf-8") + Path("frontend/workspace.js").read_text(encoding="utf-8")
    assert "/saas/organizations" in html and "textContent" in html
    assert "synthetic-demo" not in html

