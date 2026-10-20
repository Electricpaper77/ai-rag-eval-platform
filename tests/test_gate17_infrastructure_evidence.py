from __future__ import annotations

import json
from pathlib import Path

from scripts.gate17_claims_audit import audit_claims
from scripts.gate17_evidence_integrity import REQUIRED_GATES, validate_registry
from scripts.gate17_resume_bullets import generate_bullets
from scripts.gate17_scorecard import build_scorecard


ROOT = Path(__file__).resolve().parents[1]


def registry() -> dict:
    return json.loads((ROOT / "evidence/infrastructure/gates.json").read_text(encoding="utf-8"))


def test_registry_schema_and_required_gates():
    data = registry()
    assert not validate_registry(data)
    assert {entry["gate"] for entry in data["gates"]} == REQUIRED_GATES
    assert data["baseline_sha"] == "22f309627baa1de09b27a4cd829111f2e8823913"


def test_gate13_is_blocked_without_hardware_evidence():
    gate13 = next(entry for entry in registry()["gates"] if entry["gate"] == "13")
    assert gate13["status"] == "BLOCKED"
    assert gate13["evidence_level"] == "BLOCKED"
    assert gate13["executed_evidence"] == []


def test_claims_policy_rejects_unsupported_and_allows_bounded_text(tmp_path):
    data = registry()
    bad = tmp_path / "bad.md"
    bad.write_text("I performed production Kubernetes administration and ran MI300 workloads.", encoding="utf-8")
    result = audit_claims(data, [bad])
    assert result["status"] == "FAIL"
    good = tmp_path / "good.md"
    good.write_text("Disposable kind runtime validation completed; AMD hardware remains blocked.", encoding="utf-8")
    assert audit_claims(data, [good])["status"] == "PASS"


def test_claims_policy_can_allow_explicit_hardware_registry(tmp_path):
    data = registry()
    data["gates"].append({"gate": "synthetic", "status": "PASS", "evidence_level": "REAL_HARDWARE", "executed_evidence": ["AMD GPU hardware model and synchronized ROCm compute"]})
    claim = tmp_path / "gate17-hardware-claim.md"
    claim.write_text("MI300 multi-GPU inference and AMD GPU workload execution were measured.", encoding="utf-8")
    result = audit_claims(data, [claim])
    assert result["status"] == "PASS"


def test_scorecard_is_machine_readable_and_non_subjective():
    scorecard = build_scorecard(registry())
    assert "13" in scorecard["blocked_gates"]
    assert scorecard["real_hardware_validated_gates"] == []
    assert scorecard["production_validated_gates"] == []
    assert scorecard["claims_audit"] == "PASS"


def test_resume_bullets_are_bounded_and_avoid_unsupported_claims():
    bullets = generate_bullets(registry())
    all_bullets = [bullet for section in bullets.values() for bullet in section]
    assert len(all_bullets) == 8
    assert all(len(bullet) <= 180 for bullet in all_bullets)
    text = " ".join(all_bullets).lower()
    assert "production gpu" not in text
    assert "mi300" not in text
    assert "zero downtime" not in text
