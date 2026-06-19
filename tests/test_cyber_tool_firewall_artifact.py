from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = REPO_ROOT / "artifacts" / "agenttrust_iq" / "cyber_tool_firewall_eval.jsonl"
REQUIRED_FIELDS = {
    "case_id",
    "input",
    "attack_type",
    "tool_requested",
    "risk_level",
    "policy_decision",
    "expected_decision",
    "passed",
    "reason",
    "latency_ms",
}


def test_cyber_tool_firewall_jsonl_artifact_contract() -> None:
    assert ARTIFACT_PATH.exists()

    records = [
        json.loads(line)
        for line in ARTIFACT_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(records) == 40
    assert all(REQUIRED_FIELDS <= set(record) for record in records)
    assert all(record["policy_decision"] == record["expected_decision"] for record in records)
    assert all(record["passed"] is True for record in records)

    decision_counts = Counter(record["policy_decision"] for record in records)
    assert decision_counts["Block"] >= 15
    assert decision_counts["Escalate"] >= 10
    assert decision_counts["Release"] >= 15
