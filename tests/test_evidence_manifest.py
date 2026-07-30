import hashlib
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
    homepage = (ROOT / "index.html").read_text()
    readme = (ROOT / "README.md").read_text()
    for text in (homepage, readme):
        assert f"{canonical['passed_cases']} / {canonical['total_cases']}" in text
        assert "0.0%" in text
        assert "100.0%" in text
        assert f"{canonical['latency_p95_ms']} ms" in text
    assert "40 / 46" not in homepage + readme and "56 / 56" not in homepage + readme

def test_claim_policy_integrity_and_artifact_contracts():
    manifest = json.loads((ROOT / "docs/artifacts/evidence_manifest.json").read_text())
    for suite in manifest["suites"]:
        for artifact in suite["artifact_paths"]:
            path = ROOT / artifact
            assert path.exists()
        primary = ROOT / suite["artifact_paths"][0]
        if suite.get("sha256"):
            assert hashlib.sha256(primary.read_bytes()).hexdigest() == suite["sha256"]
        if primary.suffix == ".jsonl":
            rows = [json.loads(line) for line in primary.read_text().splitlines() if line.strip()]
            cases = [row for row in rows if row.get("record_type") == "case"] or rows
            assert len(cases) == suite["case_count"]
        if suite["evidence_type"] in {"mock", "simulated"}:
            assert suite["production_claim_allowed"] is False
        if suite["evidence_type"] == "not_run":
            assert not suite["metrics"]
