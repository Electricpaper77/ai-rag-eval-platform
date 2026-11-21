"""Deterministic, local-only Gate 39 inference reliability benchmark.

This benchmark intentionally models an inference adapter instead of claiming a
physical GPU result.  The answer key is kept in the runner and is never passed
to the diagnosis function.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

CAUSES = {"none", "http_429", "timeout", "latency_throttle"}


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    expected_failure: str
    observed_status: str
    latency_ms: float
    recovery_ms: float
    cost_usd: float
    diagnosis_signals: tuple[str, ...]


def scenarios() -> tuple[Scenario, ...]:
    return (
        Scenario("gate39-success", "none", "success", 42.0, 0.0, 0.00042, ("200",)),
        Scenario("gate39-http-429", "http_429", "error", 18.0, 120.0, 0.00018, ("429", "retry_after")),
        Scenario("gate39-timeout", "timeout", "error", 1000.0, 250.0, 0.00010, ("deadline_exceeded",)),
        Scenario("gate39-latency-throttle", "latency_throttle", "success", 850.0, 0.0, 0.00085, ("queue_delay", "throttled")),
    )


def _diagnose(observed_failure: str, signals: Iterable[str]) -> str:
    """Diagnosis-only interface; it receives observations, never expected_failure."""
    signal_text = set(signals)
    if observed_failure == "success":
        return "latency_throttle" if "queue_delay" in signal_text else "none"
    if "429" in signal_text:
        return "http_429"
    if "deadline_exceeded" in signal_text:
        return "timeout"
    return "unknown"


def score_diagnosis(expected_failure: str, diagnosis: str) -> float:
    """Score an independently supplied diagnosis; no answer-key lookup occurs here."""
    return 1.0 if diagnosis == expected_failure else 0.0


def _hash_record(record: dict[str, Any]) -> str:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


REQUIRED_EVIDENCE_FIELDS = {
    "run_id", "scenario_id", "model", "endpoint", "environment", "timestamp",
    "code_revision", "expected_failure", "observed_failure", "diagnosis", "score",
    "latency_ms", "error_rate", "recovery_time_ms", "approx_cost_per_request_usd",
    "evidence_sha256",
}


def validate_evidence(records: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    """Return integrity failures without consulting the answer-key artifact."""
    errors: list[str] = []
    ids = [record.get("scenario_id") for record in records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate scenario_id")
    if summary.get("scenario_count") != len(records):
        errors.append("scenario_count mismatch")
    for record in records:
        missing = REQUIRED_EVIDENCE_FIELDS - record.keys()
        if missing:
            errors.append(f"missing fields: {','.join(sorted(missing))}")
        supplied_hash = record.get("evidence_sha256")
        unsigned = {key: value for key, value in record.items() if key != "evidence_sha256"}
        if supplied_hash != _hash_record(unsigned):
            errors.append(f"invalid hash: {record.get('scenario_id')}")
        if record.get("recovery_time_ms", 0) < 0:
            errors.append(f"recovery failure: {record.get('scenario_id')}")
    return errors


def run_benchmark(output_dir: Path, *, run_id: str | None = None, environment: str = "local-simulated") -> dict[str, Any]:
    run_id = run_id or f"gate39-{uuid.uuid4().hex[:12]}"
    timestamp = datetime.now(timezone.utc).isoformat()
    revision = os.getenv("GIT_COMMIT", "unknown")
    evidence_path = output_dir / "gate39_evidence.jsonl"
    summary_path = output_dir / "gate39_summary.json"
    answer_key_path = output_dir / "gate39_answer_key.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    answer_lines: list[str] = []
    for scenario in scenarios():
        observed_failure = scenario.observed_status
        diagnosis = _diagnose(observed_failure, scenario.diagnosis_signals)
        record = {
            "benchmark": "gate39_ai_infrastructure_reliability",
            "run_id": run_id,
            "scenario_id": scenario.scenario_id,
            "model": "deterministic-mock-v1",
            "endpoint": "mock://inference",
            "environment": environment,
            "execution_mode": "simulated_gpu_behavior",
            "timestamp": timestamp,
            "code_revision": revision,
            "expected_failure": scenario.expected_failure,
            "observed_failure": observed_failure,
            "diagnosis": diagnosis,
            "diagnosis_correct": diagnosis == scenario.expected_failure,
            "score": score_diagnosis(scenario.expected_failure, diagnosis),
            "latency_ms": scenario.latency_ms,
            "error_rate": 0.0 if observed_failure == "success" else 1.0,
            "recovery_time_ms": scenario.recovery_ms,
            "approx_cost_per_request_usd": scenario.cost_usd,
            "signals": list(scenario.diagnosis_signals),
        }
        record["evidence_sha256"] = _hash_record(record)
        records.append(record)
        # Separate answer-key artifact; never read by _diagnose.
        answer_lines.append(json.dumps({"run_id": run_id, "scenario_id": scenario.scenario_id, "known_root_cause": scenario.expected_failure}, sort_keys=True))
    evidence_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")
    answer_key_path.write_text("\n".join(answer_lines) + "\n", encoding="utf-8")
    summary = {
        "benchmark": "gate39_ai_infrastructure_reliability",
        "run_id": run_id,
        "environment": environment,
        "execution_mode": "simulated_gpu_behavior",
        "physical_gpu_verified": False,
        "platform": platform.platform(),
        "scenario_count": len(records),
        "diagnosis_accuracy": round(sum(r["score"] for r in records) / len(records), 4),
        "error_rate": round(sum(r["error_rate"] for r in records) / len(records), 4),
        "latency_ms": {"min": min(r["latency_ms"] for r in records), "max": max(r["latency_ms"] for r in records)},
        "recovery_time_ms": {"max": max(r["recovery_time_ms"] for r in records)},
        "approx_cost_per_request_usd": round(sum(r["approx_cost_per_request_usd"] for r in records) / len(records), 8),
        "evidence_path": str(evidence_path),
        "answer_key_path": str(answer_key_path),
        "unsupported_environment": environment not in {"local-simulated", "test"},
        "release_verdict": "HOLD",
        "hold_reasons": ["simulated-only; no physical GPU or production deployment verification"],
    }
    summary["integrity_errors"] = validate_evidence(records, summary)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/gate39"))
    args = parser.parse_args()
    summary = run_benchmark(args.output_dir)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
