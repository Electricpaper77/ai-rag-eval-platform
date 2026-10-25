import json
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="Playwright is provisioned by the mandatory Gate 23F workflow")
from playwright.sync_api import expect, sync_playwright

from test_gate23d_browser import investigation_environment


pytestmark = pytest.mark.postgres_integration


def _add_axe(page):
    axe_path = Path("node_modules/axe-core/axe.min.js").resolve()
    assert axe_path.exists(), f"axe-core was not installed: {axe_path}"
    page.add_script_tag(path=str(axe_path))


def _audit_accessibility(page):
    result = page.evaluate("""async () => {
        const report = await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa']}});
        return report.violations.map((item) => ({id: item.id, impact: item.impact, help: item.help, nodes: item.nodes.length}));
    }""")
    severe = [item for item in result if item["impact"] in {"critical", "serious"}]
    assert not severe, {"accessibility_violations": severe}
    return result


def _assert_controls_reachable(page):
    assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
    controls = page.locator("button, input, select, textarea, a")
    for index in range(controls.count()):
        control = controls.nth(index)
        if control.is_visible():
            control.scroll_into_view_if_needed()
            box = control.bounding_box()
            assert box and box["width"] >= 44 and box["height"] >= 44, {"index": index, "box": box}
            assert control.get_attribute("aria-label") or control.text_content() or control.get_attribute("title"), index


def test_accessible_keyboard_journey_and_truthful_evidence(investigation_environment, tmp_path):
    base_url, cookies_a, _cookies_b = investigation_environment
    origin = base_url.split("/saas-workspace.html", 1)[0]
    url = origin + "/saas-workspace23e.html"
    evidence = {"schema": "gate23f-accessibility-v1", "synthetic_only": True, "viewports": [], "axe": []}
    artifact_dir = Path("artifacts/gate23f")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_cookies([{"name": name, "value": value, "url": origin} for name, value in cookies_a.items()])
        page = context.new_page()
        page.goto(url)
        page.get_by_role("button", name="Create organization").last.click()
        page.get_by_label("Organization").locator("option:not([disabled])").first.wait_for(state="attached")
        page.get_by_role("button", name="Create project").last.click()
        page.get_by_label("Project").locator("option:not([disabled])").first.wait_for(state="attached")
        page.get_by_role("button", name="Submit synthetic evaluation").click()
        page.get_by_text("Evaluation persisted.").wait_for()
        page.get_by_role("button", name="Record policy decision").click()
        page.get_by_text("Decision persisted:").wait_for()
        page.get_by_role("button", name="Investigation").click()
        page.get_by_role("button", name="Load persisted cases").click()
        page.get_by_text("MISSING_EVIDENCE").or_(page.get_by_text("Persisted case evidence")).wait_for()
        _add_axe(page)
        evidence["axe"] = _audit_accessibility(page)

        for width in (320, 390, 768, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(100)
            _assert_controls_reachable(page)
            page.screenshot(path=str(artifact_dir / f"gate23f-{width}.png"), full_page=True)
            evidence["viewports"].append({"width": width, "scroll_width": page.evaluate("() => document.documentElement.scrollWidth"), "screenshot": f"gate23f-{width}.png"})

        for label, heading in (("Projects", "Projects"), ("Evaluations", "Evaluations"), ("Scorecards", "Reliability scorecards"), ("Investigation", "Case investigation"), ("Release reviews", "Release reviews"), ("Settings", "Settings"), ("Dashboard", "Workspace dashboard")):
            page.get_by_role("button", name=label).scroll_into_view_if_needed()
            page.get_by_role("button", name=label).click()
            expect(page.get_by_role("heading", name=heading)).to_be_visible()
            page.keyboard.press("Tab")
            assert page.evaluate("() => document.activeElement !== document.body")

        Path("artifacts/gate23f/accessibility.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        context.close()
        browser.close()


def test_retry_and_failure_injection_are_actionable_and_idempotent(investigation_environment):
    base_url, cookies_a, _cookies_b = investigation_environment
    origin = base_url.split("/saas-workspace.html", 1)[0]
    url = origin + "/saas-workspace23e.html"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_cookies([{"name": name, "value": value, "url": origin} for name, value in cookies_a.items()])
        page = context.new_page()

        page.route("**/saas/organizations", lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"quarantined"}'))
        page.goto(url)
        expect(page.get_by_text("Database target is quarantined or unavailable.")).to_be_visible()
        expect(page.get_by_role("button", name="Retry")).to_be_visible()
        page.unroute("**/saas/organizations")

        malformed = lambda route: route.fulfill(status=200, content_type="application/json", body="not-json")
        page.route("**/saas/organizations", malformed)
        page.get_by_role("button", name="Retry").click()
        expect(page.get_by_text("The server returned invalid data. Retry the request.")).to_be_visible()
        page.unroute("**/saas/organizations")

        page.route("**/saas/organizations", lambda route: route.fulfill(status=401, content_type="application/json", body='{"detail":"expired"}'))
        page.get_by_role("button", name="Retry").click()
        expect(page.get_by_text("Your session expired. Authenticate through OIDC first.")).to_be_visible()
        page.unroute("**/saas/organizations")

        page.get_by_role("button", name="Retry").click()
        page.get_by_role("button", name="Create organization").last.click()
        page.get_by_label("Organization").locator("option:not([disabled])").first.wait_for(state="attached")
        page.get_by_role("button", name="Create project").last.click()
        page.get_by_label("Project").locator("option:not([disabled])").first.wait_for(state="attached")

        keys = []
        first = True

        def fail_once(route):
            nonlocal first
            keys.append(route.request.headers.get("idempotency-key"))
            if first:
                first = False
                route.fulfill(status=503, content_type="application/json", body='{"detail":"transient"}')
            else:
                route.continue_()

        page.route("**/saas/projects/*/evaluations", fail_once)
        page.get_by_role("button", name="Submit synthetic evaluation").click()
        expect(page.get_by_text("Database target is quarantined or unavailable.")).to_be_visible()
        page.get_by_role("button", name="Retry").click()
        expect(page.get_by_text("Evaluation persisted.")).to_be_visible()
        assert len(keys) == 2 and keys[0] and keys[0] == keys[1]
        page.unroute("**/saas/projects/*/evaluations")
        context.close()
        browser.close()
