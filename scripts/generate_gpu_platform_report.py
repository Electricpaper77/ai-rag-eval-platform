#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

BENCHMARK = Path("artifacts/proof/benchmark_runs.jsonl")
ROUTING = Path("artifacts/proof/routing_decisions.jsonl")
AUTOSCALE = Path("artifacts/proof/autoscaling_recommendations.jsonl")
ADMISSION = Path("artifacts/proof/admission_failures.jsonl")
SUMMARY = Path("artifacts/proof/gpu_platform_summary.json")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = int((pct / 100) * (len(values) - 1))
    return values[idx]


def main() -> int:
    benchmark_rows = read_jsonl(BENCHMARK)
    routing_rows = read_jsonl(ROUTING)
    autoscale_rows = read_jsonl(AUTOSCALE)
    admission_rows = read_jsonl(ADMISSION)

    latencies = [float(x.get("latency_ms", 0.0)) for x in benchmark_rows if x.get("status") == "ok"]
    tps = [float(x.get("tokens_per_sec", 0.0)) for x in benchmark_rows if x.get("status") == "ok"]

    summary = {
        "artifact_paths": {
            "benchmark_runs": str(BENCHMARK),
            "routing_decisions": str(ROUTING),
            "autoscaling_recommendations": str(AUTOSCALE),
            "admission_failures": str(ADMISSION),
        },
        "metrics": {
            "p50_latency_ms": round(percentile(latencies, 50), 2),
            "p95_latency_ms": round(percentile(latencies, 95), 2),
            "avg_tokens_per_sec": round(sum(tps) / max(len(tps), 1), 2),
            "success_rate": round(len(latencies) / max(len(benchmark_rows), 1), 3),
            "queue_rejection_rate": round(len(admission_rows) / max(len(routing_rows), 1), 3),
        },
        "counts": {
            "benchmark_rows": len(benchmark_rows),
            "routing_rows": len(routing_rows),
            "autoscale_rows": len(autoscale_rows),
            "admission_rows": len(admission_rows),
        },
    }

    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
