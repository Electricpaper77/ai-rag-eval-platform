import functools
import http.server
import threading
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

@pytest.fixture(scope="module")
def browser_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory="frontend")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 8765), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield "http://127.0.0.1:8765/saas-workspace.html"
    server.shutdown(); thread.join(timeout=3)

def test_synthetic_workspace_browser_journey(browser_url, tmp_path):
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        evidence = Path(".pytest_tmp/gate23a")
        evidence.mkdir(parents=True, exist_ok=True)
        page.goto(browser_url); page.screenshot(path=str(evidence / "workspace-mobile.png"), full_page=True)
        assert page.get_by_text("NON-PRODUCTION · SYNTHETIC DEMO").is_visible()
        page.get_by_role("button", name="Projects").click(); assert page.get_by_role("cell", name="Groundedness Demo").is_visible()
        page.get_by_role("button", name="Evaluations").click(); assert page.get_by_text("Submit synthetic evaluation").is_visible()
        page.get_by_role("button", name="Results").click(); assert page.get_by_text("Results and evidence").is_visible()
        browser.close()

