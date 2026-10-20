from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.gate17_claims_audit import audit_claims
from scripts.gate18_link_audit import audit_links
from scripts.verify_portfolio import verify


ROOT = Path(__file__).resolve().parents[1]


def test_readme_has_recruiter_sections_and_links():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in ("What it does", "Key validated capabilities", "Evidence", "Architecture", "Run locally", "Scope / limitations"):
        assert f"## {heading}" in readme
    for target in ("evidence/infrastructure/gates.json", "docs/INFRASTRUCTURE_CASE_STUDY.md", "docs/ARCHITECTURE.md"):
        assert target in readme


def test_architecture_capability_and_release_manifests():
    assert (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8").find("```mermaid") >= 0
    capabilities = json.loads((ROOT / "evidence/project-capabilities.json").read_text(encoding="utf-8"))
    assert capabilities["project"] == "AgentTrust IQ"
    assert capabilities["release_candidate"] is True
    assert capabilities["blocked"] == ["13"]
    release = json.loads((ROOT / "release/agenttrust-iq-release.json").read_text(encoding="utf-8"))
    for key in ("name", "baseline_sha", "release_sha", "test_total", "xfailed", "evidence_registry", "case_study", "architecture", "blocked_items", "limitations"):
        assert key in release
    assert release["release_sha"] == ""


def test_gate13_is_blocked():
    registry = json.loads((ROOT / "evidence/infrastructure/gates.json").read_text(encoding="utf-8"))
    gate13 = next(item for item in registry["gates"] if item["gate"] == "13")
    assert gate13["status"] == "BLOCKED"
    assert gate13["evidence_level"] == "BLOCKED"


def test_claims_and_links_pass_for_release_documents():
    registry = json.loads((ROOT / "evidence/infrastructure/gates.json").read_text(encoding="utf-8"))
    files = [ROOT / name for name in ("README.md", "docs/INFRASTRUCTURE_CASE_STUDY.md", "docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md", "docs/ARCHITECTURE.md")]
    assert audit_claims(registry, files)["status"] == "PASS"
    assert audit_links(files)["status"] == "PASS"


def test_portfolio_verification_script_passes():
    result = subprocess.run([sys.executable, "scripts/verify_portfolio.py"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PORTFOLIO_VERIFICATION: PASS" in result.stdout
