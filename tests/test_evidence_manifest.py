import json
from pathlib import Path
from scripts.build_evidence_summary import ROOT, build, validate

def test_manifest_and_generated_summary_are_current():
    data = json.loads((ROOT / "docs/artifacts/evidence_manifest.json").read_text())
    validate(data)
    summary, markdown = build(data)
    assert json.loads((ROOT / "docs/artifacts/evidence_summary.json").read_text()) == summary
    assert (ROOT / "docs/artifacts/EVIDENCE_SUMMARY.md").read_text() == markdown

def test_homepage_and_readme_use_only_canonical_metrics():
    canonical = json.loads((ROOT / "docs/artifacts/eval_runs/hiring_eval_summary.json").read_text())
    text = (ROOT / "index.html").read_text() + (ROOT / "README.md").read_text()
    assert f"{canonical['passed_cases']} / {canonical['total_cases']}" in text
    assert f"{canonical['latency_p95_ms']} ms" in text
    assert "40 / 46" not in text and "56 / 56" not in text
