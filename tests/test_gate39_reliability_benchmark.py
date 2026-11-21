import json

from scripts.gate39_reliability_benchmark import _diagnose, run_benchmark, score_diagnosis, validate_evidence


def test_gate39_emits_metrics_and_separate_answer_key(tmp_path):
    summary = run_benchmark(tmp_path, run_id="run-fixed", environment="test")
    evidence = (tmp_path / "gate39_evidence.jsonl").read_text().splitlines()
    answer_key = (tmp_path / "gate39_answer_key.jsonl").read_text().splitlines()
    assert summary["scenario_count"] == 4
    assert summary["diagnosis_accuracy"] == 1.0
    assert summary["execution_mode"] == "simulated_gpu_behavior"
    assert len(evidence) == len(answer_key) == 4
    assert all("known_root_cause" not in line for line in evidence)
    assert all(json.loads(line)["evidence_sha256"] for line in evidence)
    assert summary["integrity_errors"] == []


def test_gate39_covers_success_failure_and_recovery(tmp_path):
    run_benchmark(tmp_path, run_id="run-fixed")
    records = [json.loads(line) for line in (tmp_path / "gate39_evidence.jsonl").read_text().splitlines()]
    assert any(r["observed_failure"] == "success" for r in records)
    assert any(r["observed_failure"] == "error" for r in records)
    assert max(r["recovery_time_ms"] for r in records) > 0
    assert {r["expected_failure"] for r in records} >= {"http_429", "timeout", "latency_throttle"}


def test_gate39_is_explicitly_not_a_physical_gpu_result(tmp_path):
    summary = run_benchmark(tmp_path, run_id="run-fixed")
    assert summary["physical_gpu_verified"] is False
    assert summary["release_verdict"] == "HOLD"


def test_gate39_marks_unknown_environment_unsupported(tmp_path):
    summary = run_benchmark(tmp_path, run_id="run-fixed", environment="physical-gpu-unavailable")
    assert summary["unsupported_environment"] is True


def test_gate39_scores_incorrect_and_unknown_diagnoses_without_answer_key():
    assert score_diagnosis("timeout", "http_429") == 0.0
    assert _diagnose("error", ("unclassified_signal",)) == "unknown"


def test_gate39_integrity_validator_detects_missing_invalid_and_recovery_failure(tmp_path):
    run_benchmark(tmp_path, run_id="run-fixed")
    records = [json.loads(line) for line in (tmp_path / "gate39_evidence.jsonl").read_text().splitlines()]
    summary = json.loads((tmp_path / "gate39_summary.json").read_text())
    records[0]["evidence_sha256"] = "tampered"
    del records[1]["latency_ms"]
    records[2]["recovery_time_ms"] = -1
    records[3]["scenario_id"] = records[0]["scenario_id"]
    errors = validate_evidence(records, summary)
    assert any("invalid hash" in error for error in errors)
    assert any("missing fields" in error for error in errors)
    assert any("recovery failure" in error for error in errors)
    assert any("duplicate scenario_id" in error for error in errors)
