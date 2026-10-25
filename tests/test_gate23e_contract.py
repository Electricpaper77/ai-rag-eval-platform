from pathlib import Path


def test_gate23e_workspace_contract_is_accessible_and_responsive():
    html = Path("frontend/saas-workspace.html").read_text(encoding="utf-8")
    js = Path("frontend/workspace23e.js").read_text(encoding="utf-8")
    css = Path("frontend/workspace23e.css").read_text(encoding="utf-8")
    assert 'aria-label="Organization"' in html and 'aria-label="Project"' in html
    for label in ("Create organization", "Create project", "Submit synthetic evaluation", "Record policy decision", "Create release review"):
        assert label in js
    assert "MISSING_EVIDENCE" in js
    assert "credentials: \"same-origin\"" in js
    assert "@media (max-width:359px)" in css and "@media (max-width:767px)" in css
    assert "prefers-reduced-motion" in css and "focus-visible" in css

