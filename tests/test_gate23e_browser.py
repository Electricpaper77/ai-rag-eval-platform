import hashlib
import json
import os
from pathlib import Path

import psycopg
import pytest

pytest.importorskip("playwright", reason="Playwright is provisioned by the mandatory Gate 23E workflow")
from playwright.sync_api import sync_playwright

from test_gate23d_browser import investigation_environment


pytestmark = pytest.mark.postgres_integration


def test_authenticated_onboarding_persists_journey_across_viewports_and_tenants(investigation_environment, monkeypatch):
    base_url, cookies_a, cookies_b = investigation_environment
    origin = base_url.split("/saas-workspace.html", 1)[0]
    base_url = origin + "/saas-workspace23e.html"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_cookies([{"name": name, "value": value, "url": origin} for name, value in cookies_a.items()])
        page = context.new_page()
        page.goto(base_url)
        page.get_by_role("button", name="Create organization").last.click()
        page.get_by_label("Organization").locator("option:not([disabled])").first.wait_for(state="attached")
        page.get_by_role("button", name="Create project").last.click()
        page.get_by_label("Project").locator("option:not([disabled])").first.wait_for(state="attached")
        page.get_by_role("button", name="Submit synthetic evaluation").click()
        page.get_by_text("Evaluation persisted.").wait_for()
        page.get_by_role("button", name="Record policy decision").click()
        page.get_by_text("Decision persisted:").wait_for()
        page.get_by_role("button", name="Create release review").click()
        page.get_by_text("Non-production release review persisted.").wait_for()

        org_id = page.get_by_label("Organization").input_value()
        project_id = page.get_by_label("Project").input_value()
        page.get_by_role("button", name="Evaluations").click()
        run_id = page.locator(".record-card strong").first.text_content()
        assert run_id

        evidence = {"source": "synthetic_test_case", "citation": "fixture-only"}
        digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with psycopg.connect(os.environ["AGENTTRUST_POSTGRES_URL"]) as conn:
            conn.execute("INSERT INTO evaluation_cases VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", ("case_gate23e", org_id, project_id, run_id, "case-1", "failed", "groundedness", 0.1, json.dumps(evidence), digest, "synthetic_test", "2026-01-01T00:00:00+00:00"))
            conn.commit()

        page.get_by_role("button", name="Investigation").click()
        page.get_by_role("button", name="Load persisted cases").click()
        page.get_by_text("Persisted case evidence").wait_for()
        page.get_by_text("case-1").wait_for()
        page.get_by_placeholder("Reviewer comment").fill("Synthetic evidence reviewed in the non-production fixture.")
        page.get_by_role("button", name="Save reviewer annotation").click()
        page.get_by_text("Reviewer annotation persisted.").wait_for()
        page.get_by_role("button", name="Release reviews").click()
        page.get_by_text("Export sanitized JSON evidence").wait_for()

        page.reload()
        page.get_by_text("Journey complete for this tenant/project.").wait_for()
        screenshots = []
        for width in (320, 390, 768, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(100)
            overflow = page.evaluate("""() => {
                const offenders = [...document.querySelectorAll('*')].map((el) => {
                    const rect = el.getBoundingClientRect();
                    return {tag: el.tagName, cls: typeof el.className === 'string' ? el.className : '', left: rect.left, right: rect.right, width: rect.width};
                }).filter((item) => item.left < -1 || item.right > window.innerWidth + 1).slice(0, 8);
                return {scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth, offenders};
            }""")
            assert overflow["scrollWidth"] <= overflow["innerWidth"], overflow
            assert page.get_by_role("heading", name="Guided first run").is_visible()
            path = f"artifacts/gate23e/onboarding-{width}.png"
            page.screenshot(path=path, full_page=True)
            screenshots.append({"viewport_width": width, "path": path})
        page.get_by_role("button", name="Dashboard").focus()
        page.keyboard.press("Tab")
        assert page.evaluate("() => document.activeElement && document.activeElement !== document.body")

        context_b = browser.new_context(viewport={"width": 390, "height": 844})
        context_b.add_cookies([{"name": name, "value": value, "url": origin} for name, value in cookies_b.items()])
        page_b = context_b.new_page()
        denied = page_b.request.get(f"{origin}/saas/evaluations/{run_id}/cases?organization_id={org_id}&project_id={project_id}")
        assert denied.status in (403, 404)
        monkeypatch.setenv("AGENTTRUST_RESTORE_TARGET_DB", "gate23e-quarantined")
        quarantined = page.request.get(f"{origin}/saas/organizations")
        assert quarantined.status == 503
        monkeypatch.delenv("AGENTTRUST_RESTORE_TARGET_DB", raising=False)
        Path("artifacts/gate23e").mkdir(parents=True, exist_ok=True)
        Path("artifacts/gate23e/results.json").write_text(json.dumps({"schema": "gate23e-evidence-v1", "synthetic_only": True, "authenticated_journey": ["organization", "project", "evaluation", "decision", "investigation", "annotation", "release_review", "refresh"], "cross_tenant_status": denied.status, "quarantine_status": quarantined.status, "viewports": screenshots}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        context_b.close()
        context.close()
        browser.close()

