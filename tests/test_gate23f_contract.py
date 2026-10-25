from pathlib import Path


def test_gate23f_contract_has_truthful_accessibility_and_failure_evidence_hooks():
    js = Path("frontend/workspace23e.js").read_text(encoding="utf-8")
    css = Path("frontend/workspace23e.css").read_text(encoding="utf-8")
    assert "The server returned invalid data. Retry the request." in js
    assert "The network connection was lost. Check connectivity and retry." in js
    assert "cache: \"no-store\"" in js
    assert "operationKey" in js
    assert "focus({ preventScroll: true })" in js
    assert "focus-visible" in css and "prefers-reduced-motion" in css
