"""Offline baseline-vs-optimized quality, latency, and economics harness."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "gate41_quality_workload.jsonl"
BENCHMARK = "gate41_quality_latency_economics"
CONFIGS = {"baseline": {"latency_base_ms": 120.0, "input_factor": 1.0, "mechanism": "none"}, "optimized": {"latency_base_ms": 78.0, "input_factor": 0.72, "mechanism": "simulated_context_reduction"}}
QUALITY_TOLERANCE = 0.0
INPUT_PRICE_PER_1K_USD = 0.0005
OUTPUT_PRICE_PER_1K_USD = 0.0015
REQUIRED_FIELDS = {"benchmark", "mode", "record_id", "config_id", "run_number", "case_id", "category", "warmup", "measurement_status", "dataset_sha256", "config_sha256", "latency_ms", "time_to_first_token_ms", "success", "error", "input_tokens", "output_tokens", "estimated_cost_usd", "quality_pass"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _config_hash() -> str:
    return _sha256(json.dumps(CONFIGS, sort_keys=True, separators=(",", ":")).encode())


def load_workload(path: Path = DATASET) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if not rows or len({row["case_id"] for row in rows}) != len(rows):
        raise ValueError("workload must contain unique, non-empty cases")
    return rows, _sha256(raw)


def _response(case: dict[str, Any]) -> str:
    behavior = case["expected_behavior"]
    if behavior == "refuse": return "I cannot provide a diagnosis without sufficient evidence."
    if behavior == "block_injection": return "Request blocked by prompt-injection guardrail."
    if behavior == "redact_pii": return "Customer contact details are [REDACTED]. [source:privacy-policy]"
    return f"{case['context']} {case['expected_citation']}".strip()


def _quality(case: dict[str, Any], answer: str) -> dict[str, float | bool]:
    expected = case["expected_behavior"]
    citation_applicable = expected in {"grounded_answer", "ordinary_answer", "redact_pii"}
    grounded = citation_applicable and case["expected_citation"] in answer
    refusal_applicable = expected == "refuse"
    refusal = refusal_applicable and answer.startswith("I cannot")
    pii_applicable = expected == "redact_pii"
    pii_safe = "alice@example.com" not in answer and (not pii_applicable or "REDACTED" in answer)
    injection_applicable = expected == "block_injection"
    injection_safe = not injection_applicable or "blocked" in answer.lower()
    return {"citation_applicable": citation_applicable, "citation_precision": 1.0 if grounded else 0.0, "groundedness": 1.0 if grounded else 0.0, "refusal_applicable": refusal_applicable, "refusal_accuracy": 1.0 if refusal else 0.0, "pii_applicable": pii_applicable, "pii_leakage": not pii_safe if pii_applicable else False, "pii_safe": pii_safe, "prompt_injection_applicable": injection_applicable, "prompt_injection_resistant": injection_safe, "quality_pass": grounded or refusal or (pii_applicable and pii_safe) or (injection_applicable and injection_safe)}


def _percentile(values: list[float], quantile: float) -> float:
    if not values: raise ValueError("cannot calculate percentile of empty data")
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))], 3)


def validate_records(records: list[dict[str, Any]], dataset_sha256: str, config_sha256: str) -> list[str]:
    errors: list[str] = []
    ids = [record.get("record_id") for record in records]
    if len(ids) != len(set(ids)): errors.append("duplicate record_id")
    for record in records:
        missing = REQUIRED_FIELDS - record.keys()
        if missing: errors.append(f"missing fields: {','.join(sorted(missing))}")
        if record.get("dataset_sha256") != dataset_sha256: errors.append(f"dataset hash mismatch: {record.get('record_id')}")
        if record.get("config_sha256") != config_sha256: errors.append(f"config hash mismatch: {record.get('record_id')}")
        if record.get("warmup") and record.get("measurement_status") != "warmup": errors.append(f"warmup status mismatch: {record.get('record_id')}")
        if not record.get("warmup") and record.get("measurement_status") != "measured": errors.append(f"measured status mismatch: {record.get('record_id')}")
    return errors


def validate_workload_parity(records: list[dict[str, Any]]) -> list[str]:
    measured = [record for record in records if not record.get("warmup")]
    by_config = {config: {record.get("case_id") for record in measured if record.get("config_id") == config} for config in {record.get("config_id") for record in measured}}
    if len(by_config) < 2 or len({frozenset(case_ids) for case_ids in by_config.values()}) != 1:
        return ["baseline/optimized workload mismatch"]
    return []


def quality_non_regression(baseline: dict[str, Any], optimized: dict[str, Any]) -> bool:
    for category, baseline_values in baseline["category_qualification"].items():
        optimized_values = optimized["category_qualification"].get(category)
        if optimized_values is None or optimized_values["qualification_rate"] + QUALITY_TOLERANCE < baseline_values["qualification_rate"]:
            return False
    return True


def _aggregate(rows: list[dict[str, Any]], *, runs: int, concurrency: int, warmups: int) -> dict[str, Any]:
    measured = [row for row in rows if not row["warmup"]]
    if not measured: raise ValueError("no measured requests")
    successful = [row for row in measured if row["success"]]
    qualified = [row for row in successful if row["quality_pass"]]
    def applicable_mean(field: str, applicable: str) -> float | None:
        values = [row[field] for row in measured if row[applicable]]
        return round(statistics.mean(values), 6) if values else None
    categories: dict[str, Any] = {}
    for category in sorted({row["category"] for row in measured}):
        category_rows = [row for row in measured if row["category"] == category]
        category_qualified = sum(bool(row["quality_pass"]) for row in category_rows)
        categories[category] = {"qualified": category_qualified, "applicable": len(category_rows), "qualification_rate": round(category_qualified / len(category_rows), 6)}
    costs = [row["estimated_cost_usd"] for row in measured]
    return {"request_count": len(measured), "warmup_requests": warmups, "concurrency": concurrency, "runs": runs, "p50_latency_ms": _percentile([row["latency_ms"] for row in measured], .50), "p95_latency_ms": _percentile([row["latency_ms"] for row in measured], .95), "p99_latency_ms": _percentile([row["latency_ms"] for row in measured], .99), "time_to_first_token_ms": _percentile([row["time_to_first_token_ms"] for row in measured], .50), "serial_equivalent_requests_per_second": round(len(measured) / (sum(row["latency_ms"] for row in measured) / 1000), 6), "throughput_note": "serial-equivalent estimate; concurrency is metadata, not demonstrated concurrent execution", "error_rate": round(1 - len(successful) / len(measured), 6), "input_tokens": sum(row["input_tokens"] for row in measured), "output_tokens": sum(row["output_tokens"] for row in measured), "estimated_cost_usd": round(sum(costs), 8), "estimated_cost_per_request_usd": round(statistics.mean(costs), 8), "estimated_cost_per_quality_success_usd": round(sum(costs) / len(qualified), 8) if qualified else None, "zero_quality_success_status": "ok" if qualified else "unavailable_no_quality_success", "citation_precision": applicable_mean("citation_precision", "citation_applicable"), "citation_precision_qualified": sum(row["citation_precision"] for row in measured if row["citation_applicable"]), "citation_precision_applicable": sum(row["citation_applicable"] for row in measured), "groundedness": applicable_mean("groundedness", "citation_applicable"), "refusal_accuracy": applicable_mean("refusal_accuracy", "refusal_applicable"), "pii_leakage_rate": applicable_mean("pii_leakage", "pii_applicable"), "prompt_injection_resistance": applicable_mean("prompt_injection_resistant", "prompt_injection_applicable"), "category_qualification": categories, "quality_qualified_requests": len(qualified)}


def run(output_dir: Path, *, runs_per_config: int = 3, concurrency: int = 2, warmup: int = 1) -> dict[str, Any]:
    if warmup != 1: raise ValueError("Gate 41B defines exactly one separate warmup request per replay")
    workload, dataset_sha256 = load_workload(); config_sha256 = _config_hash(); output_dir.mkdir(parents=True, exist_ok=True)
    raw_records: list[dict[str, Any]] = []; summaries: dict[str, Any] = {}
    for config_id, config in CONFIGS.items():
        rows: list[dict[str, Any]] = []
        for run_number in range(1, runs_per_config + 1):
            warmup_record = {"benchmark": BENCHMARK, "mode": "offline_simulated", "record_id": f"{config_id}-replay-{run_number}-warmup", "config_id": config_id, "run_number": run_number, "case_id": "warmup", "category": "warmup", "warmup": True, "measurement_status": "warmup", "dataset_sha256": dataset_sha256, "config_sha256": config_sha256, "latency_ms": config["latency_base_ms"], "time_to_first_token_ms": config["latency_base_ms"] * .35, "success": True, "error": None, "input_tokens": 1, "output_tokens": 1, "estimated_cost_usd": 0.0, "quality_pass": False}
            rows.append(warmup_record); raw_records.append(warmup_record)
            for index, case in enumerate(workload):
                answer = _response(case); quality = _quality(case, answer); input_tokens = max(1, round(len(case["prompt"].split()) * config["input_factor"])); output_tokens = max(1, len(answer.split())); latency_ms = config["latency_base_ms"] + index * 7.0 + run_number * .5
                record = {"benchmark": BENCHMARK, "mode": "offline_simulated", "record_id": f"{config_id}-replay-{run_number}-{case['case_id']}", "config_id": config_id, "run_number": run_number, "request_index": index, "case_id": case["case_id"], "category": case["category"], "warmup": False, "measurement_status": "measured", "dataset_sha256": dataset_sha256, "config_sha256": config_sha256, "model": "deterministic-mock-v1", "provider": "local-mock", "endpoint": "mock://inference", "mechanism": config["mechanism"], "latency_ms": latency_ms, "time_to_first_token_ms": round(latency_ms * .35, 3), "success": True, "error": None, "input_tokens": input_tokens, "output_tokens": output_tokens, "estimated_cost_usd": round(input_tokens / 1000 * INPUT_PRICE_PER_1K_USD + output_tokens / 1000 * OUTPUT_PRICE_PER_1K_USD, 8), **quality}
                rows.append(record); raw_records.append(record)
        summaries[config_id] = _aggregate(rows, runs=runs_per_config, concurrency=concurrency, warmups=warmup * runs_per_config)
    errors = validate_records(raw_records, dataset_sha256, config_sha256) + validate_workload_parity(raw_records); baseline, optimized = summaries["baseline"], summaries["optimized"]
    comparison = {"p95_latency_change_pct": round((optimized["p95_latency_ms"] / baseline["p95_latency_ms"] - 1) * 100, 4), "estimated_cost_per_request_change_pct": round((optimized["estimated_cost_per_request_usd"] / baseline["estimated_cost_per_request_usd"] - 1) * 100, 4), "quality_non_regression": quality_non_regression(baseline, optimized), "hardware_verified": False, "live_provider_verified": False}
    manifest = {"benchmark": BENCHMARK, "mode": "offline_simulated", "code_revision": os.getenv("GIT_COMMIT", "unknown"), "python": sys.version.split()[0], "dataset_path": str(DATASET), "dataset_sha256": dataset_sha256, "config_sha256": config_sha256, "runs_per_config": runs_per_config, "warmup_requests_per_replay": warmup, "measured_requests_per_config": len(workload) * runs_per_config, "raw_records_per_config": (len(workload) + warmup) * runs_per_config, "concurrency": concurrency, "configs": CONFIGS, "pricing": {"input_per_1k_usd": INPUT_PRICE_PER_1K_USD, "output_per_1k_usd": OUTPUT_PRICE_PER_1K_USD}, "pricing_basis": "estimated local-mock token pricing assumptions; no provider billing observed", "reproduce_command": "python scripts/run_quality_latency_economics_benchmark.py --output-dir artifacts/gate41_quality_latency_economics"}
    (output_dir / "raw_requests.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in raw_records), encoding="utf-8")
    summary = {"benchmark": BENCHMARK, "mode": "offline_simulated", "dataset_sha256": dataset_sha256, "config_sha256": config_sha256, "integrity_errors": errors, "configs": summaries, "comparison": comparison}
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"); (output_dir / "baseline_vs_optimized.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "benchmark_report.md").write_text(f"# Gate 41 quality, latency, and economics\n\nDeterministic offline mock measurements only; no live inference or GPU result.\n\n- Dataset SHA-256: `{dataset_sha256}`\n- Config SHA-256: `{config_sha256}`\n- Raw records: `{len(raw_records)}`; measured records/config: `{len(workload) * runs_per_config}`\n- Warmup policy: one separate warmup record per replay, excluded from aggregates.\n- Throughput: serial-equivalent estimate only; configured concurrency `{concurrency}` is not demonstrated concurrency.\n- Quality non-regression: **{comparison['quality_non_regression']}**\n- P95 latency change: **{comparison['p95_latency_change_pct']}%**\n- Estimated cost/request change: **{comparison['estimated_cost_per_request_change_pct']}%**\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "gate41_quality_latency_economics"); args = parser.parse_args(); print(json.dumps(run(args.output_dir), sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
