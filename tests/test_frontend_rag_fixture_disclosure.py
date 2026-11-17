import faulthandler
import sys
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def test_rag_fixture_disclosure_survives_scenario_updates():
    def checkpoint(label):
        print(f"GATE36M CHECKPOINT: {label}", flush=True)

    checkpoint("A test setup")
    html = (Path(__file__).parents[1] / "frontend" / "index.html").resolve().as_uri()
    if not CHROME.is_file():
        raise FileNotFoundError(f"Chrome executable not found: {CHROME}")
    faulthandler.dump_traceback_later(30, file=sys.stderr)
    with playwright.sync_playwright() as pw:
        checkpoint("B before browser launch")
        browser = pw.chromium.launch(
            headless=True, executable_path=str(CHROME), timeout=10_000
        )
        checkpoint("B browser launched")
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(5_000)
        checkpoint("C page/context created")
        page.goto(html, wait_until="domcontentloaded", timeout=10_000)
        checkpoint("D local document loaded")

        disclosure = page.locator("#simulator-fixture-disclosure")
        panel = page.locator("#simulator-panel")

        def assert_disclosure():
            assert disclosure.is_visible()
            text = disclosure.inner_text()
            assert "Simulated fixture value" in text
            assert "not a canonical benchmark" in text
            assert panel.locator("#simulator-fixture-disclosure").count() == 1

        checkpoint("E before RAG selection")
        page.locator("#simulator-tab-good").click()
        assert page.locator("#simulator-tab-good").get_attribute("aria-selected") == "true"
        assert page.locator("#simulator-decision strong").inner_text() == "Release"
        assert_disclosure()
        checkpoint("E RAG assertions complete")

        checkpoint("F before Citation Failure selection")
        page.locator("#simulator-tab-citation").click()
        assert page.locator("#simulator-tab-citation").get_attribute("aria-selected") == "true"
        assert page.locator("#simulator-decision strong").inner_text() == "Block: missing citation"
        assert_disclosure()
        checkpoint("F Citation Failure assertions complete")

        checkpoint("G before Prompt Injection selection")
        page.locator("#simulator-tab-unsafe").click()
        assert page.locator("#simulator-tab-unsafe").get_attribute("aria-selected") == "true"
        assert page.locator("#simulator-decision strong").inner_text() == "Safe refusal"
        assert_disclosure()
        checkpoint("G Prompt Injection assertions complete")

        checkpoint("H before return to RAG")
        page.locator("#simulator-tab-good").click()
        assert page.locator("#simulator-tab-good").get_attribute("aria-selected") == "true"
        assert page.locator("#simulator-decision strong").inner_text() == "Release"
        assert_disclosure()
        checkpoint("H return-to-RAG assertions complete")
        checkpoint("I before cleanup")
        context.close()
        browser.close()
        checkpoint("I cleanup complete")
    faulthandler.cancel_dump_traceback_later()
