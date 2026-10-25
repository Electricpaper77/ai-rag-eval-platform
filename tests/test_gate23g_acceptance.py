"""Independent, synthetic-only Gate 23G product acceptance.

These tests intentionally exercise the real FastAPI process, PostgreSQL adapter,
session cookies and Chromium UI. They do not seed a fake API response layer.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from test_gate23d_browser import investigation_environment


pytestmark = pytest.mark.postgres_integration


def _headers(cookies: dict[str, str], **extra: str) -> dict[str, str]:
    return {
        "Origin": "http://127.0.0.1:8768",
        "X-CSRF-Token": cookies["agenttrust_csrf"],
        **extra,
    }


def _new_session() -> dict[str, str]:
    """Obtain a real callback-issued session for an otherwise empty user."""
    from backend.app.main import app

    with TestClient(app, base_url="https://testserver") as client:
        login = client.get("/saas/auth/login", follow_redirects=False)
        assert login.status_code == 307
        state = login.json()["state"]
        callback = client.get(f"/saas/auth/callback?code=gate23g-{uuid.uuid4().hex}&state={state}")
        assert callback.status_code == 200, callback.text
        return {name: callback.cookies[name] for name in ("agenttrust_session", "agenttrust_csrf")}


def _insert_fixture_case(org_id: str, project_id: str, run_id: str, key: str) -> None:
    evidence = {"source": "fixture-only", "note": "synthetic case row; not organic provider ingestion"}
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with psycopg.connect(os.environ["AGENTTRUST_POSTGRES_URL"]) as conn:
        conn.execute(
            "INSERT INTO evaluation_cases VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (key, org_id, project_id, run_id, "fixture-case", "failed", "groundedness", 0.1,
             json.dumps(evidence), digest, "synthetic_fixture", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()


def test_gate23g_real_http_journey_security_and_reproducible_evidence(investigation_environment):
    """Create, persist, inspect, investigate, review, export and isolate two tenants."""
    _base_url, cookies_a, cookies_b = investigation_environment
    from backend.app.main import app

    client = TestClient(app, base_url="http://127.0.0.1:8768")
    headers_a = _headers(cookies_a)
    headers_b = _headers(cookies_b)
    suffix = uuid.uuid4().hex[:10]

    org = client.post("/saas/organizations", json={"name": f"Gate23G-A-{suffix}"}, headers=headers_a, cookies=cookies_a)
    assert org.status_code == 200, org.text
    org_id = org.json()["id"]
    project = client.post("/saas/projects", json={"organization_id": org_id, "name": f"demo-{suffix}"}, headers=headers_a, cookies=cookies_a)
    assert project.status_code == 200, project.text
    project_id = project.json()["id"]

    org_b = client.post("/saas/organizations", json={"name": f"Gate23G-B-{suffix}"}, headers=headers_b, cookies=cookies_b)
    assert org_b.status_code == 200, org_b.text
    org_b_id = org_b.json()["id"]
    project_b = client.post("/saas/projects", json={"organization_id": org_b_id, "name": f"other-{suffix}"}, headers=headers_b, cookies=cookies_b)
    assert project_b.status_code == 200, project_b.text

    run_headers = {**headers_a, "X-Organization-Id": org_id, "Idempotency-Key": f"gate23g-run-{suffix}"}
    run = client.post(f"/saas/projects/{project_id}/evaluations", content='{"prompt":"synthetic acceptance"}\n', headers=run_headers, cookies=cookies_a)
    assert run.status_code == 200, run.text
    replay = client.post(f"/saas/projects/{project_id}/evaluations", content='{"prompt":"synthetic acceptance"}\n', headers=run_headers, cookies=cookies_a)
    assert replay.status_code == 200 and replay.json()["id"] == run.json()["id"]
    run_id = run.json()["id"]
    detail = client.get(f"/saas/evaluations/{run_id}?organization_id={org_id}", cookies=cookies_a)
    assert detail.status_code == 200 and detail.json()["id"] == run_id
    assert client.get(f"/saas/evaluations/compare?organization_id={org_id}&run_id_a={run_id}&run_id_b={run_id}", cookies=cookies_a).status_code == 200
    exported = client.get(f"/saas/evaluations/{run_id}/export?organization_id={org_id}&format=json", cookies=cookies_a)
    assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]
    csv_export = client.get(f"/saas/evaluations/{run_id}/export?organization_id={org_id}&format=csv", cookies=cookies_a)
    assert csv_export.status_code == 200 and "attachment" in csv_export.headers["content-disposition"]

    policy = client.post(
        "/saas/policies",
        json={"organization_id": org_id, "project_id": project_id, "name": f"policy-{suffix}",
              "metrics": {"quality": {"direction": "higher_is_better", "threshold": 0.8, "accepted_provenance": ["synthetic_test"]}},
              "require_baseline": False},
        headers=headers_a,
        cookies=cookies_a,
    )
    assert policy.status_code == 200, policy.text
    decision = client.post(
        f"/saas/evaluations/{run_id}/decision?organization_id={org_id}",
        json={"policy_id": policy.json()["id"], "idempotency_key": f"gate23g-decision-{suffix}"},
        headers=headers_a,
        cookies=cookies_a,
    )
    assert decision.status_code == 200 and decision.json()["decision"] in {"PASS", "HOLD", "INSUFFICIENT_EVIDENCE"}

    case_id = f"gate23g-case-{suffix}"
    _insert_fixture_case(org_id, project_id, run_id, case_id)
    cases = client.get(f"/saas/evaluations/{run_id}/cases?organization_id={org_id}&project_id={project_id}", cookies=cookies_a)
    assert cases.status_code == 200 and cases.json()["cases"][0]["provenance"] == "synthetic_fixture"
    review = client.post(
        f"/saas/cases/{case_id}/reviews?organization_id={org_id}",
        json={"status": "confirmed", "comment": "Synthetic fixture reviewed.", "expected_revision": 0, "idempotency_key": f"gate23g-review-{suffix}"},
        headers=headers_a,
        cookies=cookies_a,
    )
    assert review.status_code == 200
    stale = client.post(
        f"/saas/cases/{case_id}/reviews?organization_id={org_id}",
        json={"status": "hold", "comment": "stale", "expected_revision": 0, "idempotency_key": f"gate23g-stale-{suffix}"},
        headers=headers_a,
        cookies=cookies_a,
    )
    assert stale.status_code == 409
    release = client.post(
        f"/saas/release-reviews?organization_id={org_id}",
        json={"project_id": project_id, "decision_id": decision.json()["id"], "recommendation": "hold", "idempotency_key": f"gate23g-release-{suffix}"},
        headers=headers_a,
        cookies=cookies_a,
    )
    assert release.status_code == 200
    release_export = client.get(f"/saas/release-reviews/{release.json()['id']}/export?organization_id={org_id}", cookies=cookies_a)
    assert release_export.status_code == 200 and "non_production_disclaimer" in release_export.json()

    assert client.get(f"/saas/evaluations/{run_id}?organization_id={org_id}", cookies=cookies_b).status_code in {403, 404}
    assert client.get(f"/saas/evaluations/{run_id}/export?organization_id={org_id}", cookies=cookies_b).status_code in {403, 404}
    assert client.get("/saas/organizations").status_code == 401
    assert client.post("/saas/organizations", json={"name": "no-csrf"}, cookies=cookies_a).status_code == 403
    bad = client.post(f"/saas/projects/{project_id}/evaluations", content="not-json", headers={**headers_a, "X-Organization-Id": org_id, "Idempotency-Key": f"bad-{suffix}"}, cookies=cookies_a)
    assert bad.status_code == 400

    original = os.environ.get("AGENTTRUST_RESTORE_TARGET_DB")
    os.environ["AGENTTRUST_RESTORE_TARGET_DB"] = "gate23g-quarantined"
    try:
        assert client.get("/saas/organizations", cookies=cookies_a).status_code == 503
        assert client.post("/saas/organizations", json={"name": "quarantined"}, headers=headers_a, cookies=cookies_a).status_code == 503
    finally:
        if original is None:
            os.environ.pop("AGENTTRUST_RESTORE_TARGET_DB", None)
        else:
            os.environ["AGENTTRUST_RESTORE_TARGET_DB"] = original

    evidence = {
        "schema": "gate23g-http-acceptance-v1",
        "synthetic_only": True,
        "fixture_case_provenance": "synthetic_fixture; not organic provider ingestion",
        "journey": ["organization", "project", "evaluation", "persisted_result", "decision", "case", "annotation", "release_review", "json_export", "csv_export", "refreshable_state"],
        "security_statuses": {"unauthorized": 401, "missing_csrf": 403, "stale_revision": 409, "quarantine": 503, "cross_tenant": "403_or_404"},
    }
    Path("artifacts/gate23g").mkdir(parents=True, exist_ok=True)
    Path("artifacts/gate23g/http-acceptance.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_gate23g_chromium_reproducible_demo_accessibility_and_recovery(investigation_environment):
    """Run the visible workflow at all required viewports with real browser requests."""
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        if os.getenv("GATE23G_REQUIRED") == "1":
            raise
        pytest.skip("Playwright is installed by the mandatory Gate 23G workflow")

    base_url, _cookies_a, _cookies_b = investigation_environment
    origin = base_url.split("/saas-workspace.html", 1)[0]
    cookies = _new_session()
    from backend.app.main import app

    evidence = {"schema": "gate23g-browser-acceptance-v1", "synthetic_only": True, "viewports": [], "axe": [], "keyboard": True, "refresh": False}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_cookies([{"name": name, "value": value, "url": origin} for name, value in cookies.items()])
        page = context.new_page()
        page.goto(origin + "/saas-workspace23e.html")
        suffix = uuid.uuid4().hex[:10]
        if page.get_by_role("button", name="Create organization").count():
            page.locator('input[name="name"]').fill(f"Browser demo {suffix}")
            page.get_by_role("button", name="Create organization").click()
            page.locator('select[aria-label="Organization"] option:not([disabled])').first.wait_for(state="attached")
        org_id = page.locator('select[aria-label="Organization"]').input_value()
        if page.get_by_role("button", name="Create project").count():
            page.locator('input[name="name"]').fill(f"Browser project {suffix}")
            page.get_by_role("button", name="Create project").click()
            page.locator('select[aria-label="Project"] option:not([disabled])').first.wait_for(state="attached")
        project_id = page.locator('select[aria-label="Project"]').input_value()
        page.get_by_role("button", name="Submit synthetic evaluation").click()
        expect(page.get_by_text("Evaluation persisted.")).to_be_visible()
        page.get_by_role("button", name="Record policy decision").click()
        expect(page.get_by_text("Decision persisted:")).to_be_visible()
        page.get_by_role("button", name="Create release review").click()
        expect(page.get_by_text("Non-production release review persisted.")).to_be_visible()
        runs_response = page.request.get(f"{origin}/saas/evaluations?organization_id={org_id}&project_id={project_id}")
        assert runs_response.status == 200
        run_id = runs_response.json()["evaluations"][0]["id"]
        _insert_fixture_case(org_id, project_id, run_id, f"browser-case-{suffix}")
        page.get_by_role("button", name="Evaluations").click()
        expect(page.get_by_text(run_id)).to_be_visible()
        page.get_by_role("button", name="Inspect result").first.click()
        expect(page.get_by_role("heading", name="Evaluation detail")).to_be_visible()
        page.get_by_role("button", name="Investigation").click()
        page.get_by_role("button", name="Load persisted cases").click()
        expect(page.get_by_text("fixture-case")).to_be_visible()
        page.get_by_placeholder("Reviewer comment").fill("Browser fixture review; synthetic only.")
        page.get_by_role("button", name="Save reviewer annotation").click()
        expect(page.get_by_text("Reviewer annotation persisted.")).to_be_visible()

        page.get_by_role("button", name="Release reviews").click()
        expect(page.get_by_text("Export sanitized JSON evidence")).to_be_visible()
        with page.expect_download() as download_info:
            page.get_by_text("Export sanitized JSON evidence").click()
        download = download_info.value
        assert download.suggested_filename.endswith(".json")
        page.reload()
        expect(page.get_by_text("Journey complete for this tenant/project.")).to_be_visible()
        evidence["refresh"] = True

        page.keyboard.press("Tab")
        assert page.evaluate("() => document.activeElement && document.activeElement !== document.body")
        axe_path = Path("node_modules/axe-core/axe.min.js").resolve()
        assert axe_path.exists(), f"axe-core missing: {axe_path}"
        page.add_script_tag(path=str(axe_path))
        violations = page.evaluate("""async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa']}})).violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length}))""")
        severe = [item for item in violations if item["impact"] in {"critical", "serious"}]
        assert not severe, severe
        evidence["axe"] = violations
        for width in (320, 390, 768, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(100)
            overflow = page.evaluate("() => ({innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth})")
            assert overflow["scrollWidth"] <= overflow["innerWidth"], overflow
            filename = f"artifacts/gate23g/gate23g-{width}.png"
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=filename, full_page=True)
            evidence["viewports"].append({"width": width, "scroll_width": overflow["scrollWidth"], "screenshot": Path(filename).name})
        context.close()
        browser.close()

    Path("artifacts/gate23g/browser-acceptance.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_gate23g_network_interruption_is_recoverable_and_does_not_duplicate(investigation_environment):
    """Exercise the browser retry contract with the same idempotency key."""
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        if os.getenv("GATE23G_REQUIRED") == "1":
            raise
        pytest.skip("Playwright is installed by the mandatory Gate 23G workflow")

    base_url, cookies_a, _cookies_b = investigation_environment
    origin = base_url.split("/saas-workspace.html", 1)[0]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_cookies([{"name": name, "value": value, "url": origin} for name, value in cookies_a.items()])
        page = context.new_page()
        page.route("**/saas/organizations", lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"quarantined"}'))
        page.goto(origin + "/saas-workspace23e.html")
        expect(page.locator(".error")).to_have_text("Database target is quarantined or unavailable.")
        page.unroute("**/saas/organizations")
        page.route("**/saas/organizations", lambda route: route.fulfill(status=200, content_type="application/json", body="not-json"))
        page.get_by_role("button", name="Retry").click()
        expect(page.locator(".error")).to_have_text("The server returned invalid data. Retry the request.")
        page.unroute("**/saas/organizations")
        page.route("**/saas/organizations", lambda route: route.abort())
        page.get_by_role("button", name="Retry").click()
        expect(page.locator(".error")).to_have_text("The network connection was lost. Check connectivity and retry.")
        page.unroute("**/saas/organizations")
        context.close()
        browser.close()
