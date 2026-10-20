from __future__ import annotations

import json
from pathlib import Path

from scripts.gate17_claims_audit import audit_claims
from scripts.gate19_claim_scan import scan_claims
from scripts.gate19_release_audit import audit_release
from scripts.gate19_release_manifest import build_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_version_and_release_documents():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "1.0.0"
    notes = (ROOT / "docs/RELEASE_NOTES_V1.md").read_text(encoding="utf-8")
    status = (ROOT / "docs/PROJECT_STATUS.md").read_text(encoding="utf-8")
    for heading in ("# AgentTrust IQ v1.0.0", "## Release Scope", "## Validated Capabilities", "## Verification", "## Known Limitations"):
        assert heading in notes
    for heading in ("## VALIDATED", "## BLOCKED", "## NOT CLAIMED"):
        assert heading in status
    for phrase in ("Gate 13", "production Kubernetes", "MI300", "multi-GPU", "production-scale infrastructure"):
        assert phrase in status


def test_gate13_and_registry_boundary():
    registry = json.loads((ROOT / "evidence/infrastructure/gates.json").read_text(encoding="utf-8"))
    gate13 = next(item for item in registry["gates"] if item["gate"] == "13")
    assert gate13["status"] == "BLOCKED"
    assert gate13["evidence_level"] == "BLOCKED"
    assert not any(item["evidence_level"] == "REAL_HARDWARE" for item in registry["gates"])


def test_prohibited_claims_are_rejected_unless_limited(tmp_path):
    registry = json.loads((ROOT / "evidence/infrastructure/gates.json").read_text(encoding="utf-8"))
    positive = tmp_path / "positive.md"
    positive.write_text("We delivered production-scale infrastructure and MI300 execution.", encoding="utf-8")
    assert scan_claims(registry, [positive])["status"] == "FAIL"
    limited = tmp_path / "limited.md"
    limited.write_text("Not claimed: production-scale infrastructure. Not claimed: MI300 execution.", encoding="utf-8")
    assert scan_claims(registry, [limited])["status"] == "PASS"
    assert audit_claims(registry, [limited])["status"] == "PASS"


def test_final_manifest_schema():
    result = build_manifest("f" * 40, "332 passed, 1 xfailed", {"health": {"status": 200}, "chat": {"status": 200}}, "a" * 40)
    required = {"project", "version", "baseline_sha", "feature_sha", "release_status", "tests_passed", "xfailed", "smoke_health_status", "smoke_chat_status", "claims_audit", "evidence_integrity", "release_audit", "gate13", "production_claimed", "real_amd_gpu_execution"}
    assert required <= result.keys()
    assert result["version"] == "1.0.0"
    assert result["release_status"] == "READY"
    assert result["gate13"] == "BLOCKED"
    assert result["production_claimed"] is False
    assert result["real_amd_gpu_execution"] is False


def test_release_audit_and_document_references_pass():
    assert audit_release(ROOT) == []
    assert (ROOT / "docs/ARCHITECTURE.md").exists()
    assert (ROOT / "docs/INFRASTRUCTURE_CASE_STUDY.md").exists()
    assert (ROOT / "docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md").exists()
