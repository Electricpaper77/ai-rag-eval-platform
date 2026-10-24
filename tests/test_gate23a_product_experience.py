from pathlib import Path

WORKSPACE = Path("frontend/saas-workspace.html")

def test_workspace_is_real_saas_shell_with_truthful_api_journey():
    html = WORKSPACE.read_text(encoding="utf-8")
    for label in ("Dashboard", "Projects", "Evaluations", "Results", "Settings"):
        assert label in html
    for endpoint in ("/saas/projects/", "/saas/projects/synthetic-demo/evaluations", "Idempotency-Key"):
        assert endpoint in html
    assert "NON-PRODUCTION" in html and "SYNTHETIC" in html
    assert "fabricated" in html.lower()

def test_workspace_does_not_claim_production_metrics_or_bypass_authentication():
    html = WORKSPACE.read_text(encoding="utf-8").lower()
    assert "oidc" in html or "authenticate" in html
    assert "gpu throughput" not in html
    assert "hallucination reduction" not in html

