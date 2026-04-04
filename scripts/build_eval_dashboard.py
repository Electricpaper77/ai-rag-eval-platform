from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ARTIFACTS_DIR = Path("artifacts/proof")
SUMMARY_PATH = ARTIFACTS_DIR / "eval_dashboard_summary.json"
COMPARISON_PATH = ARTIFACTS_DIR / "benchmark_comparison.json"


@dataclass
class RunAggregation:
    run_id: str
    model: str | None
    prompt_version: str | None
    retrieval_configuration: str | None
    temperature: float | None
    chunk_size: int | None
    rows: list[dict[str, Any]]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * percentile))
    return float(ordered[idx])


def _load_jsonl_rows(artifacts_dir: Path) -> dict[str, RunAggregation]:
    grouped: dict[str, RunAggregation] = {}

    for path in sorted(artifacts_dir.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                run_id = str(row.get("run_id") or path.stem)
                if run_id not in grouped:
                    grouped[run_id] = RunAggregation(
                        run_id=run_id,
                        model=row.get("model"),
                        prompt_version=row.get("prompt_version"),
                        retrieval_configuration=row.get("retrieval_configuration"),
                        temperature=row.get("temperature"),
                        chunk_size=row.get("chunk_size"),
                        rows=[],
                    )
                grouped[run_id].rows.append(row)

    return grouped


def _build_time_series(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed: list[tuple[int, dict[str, Any]]] = list(enumerate(rows))
    indexed.sort(key=lambda item: item[1].get("timestamp") or "")

    pass_series: list[dict[str, Any]] = []
    tps_series: list[dict[str, Any]] = []
    seen = 0
    passed = 0

    for i, row in indexed:
        seen += 1
        if bool(row.get("passed", False)):
            passed += 1
        timestamp = row.get("timestamp") or f"index-{i}"
        pass_series.append(
            {
                "timestamp": timestamp,
                "pass_rate": (passed / seen) if seen else 0.0,
            }
        )

        if row.get("tokens_per_sec") is not None:
            tps_series.append(
                {
                    "timestamp": timestamp,
                    "tokens_per_sec": float(row["tokens_per_sec"]),
                }
            )

    return pass_series, tps_series


def summarize_runs(artifacts_dir: Path = ARTIFACTS_DIR) -> dict[str, Any]:
    runs = _load_jsonl_rows(artifacts_dir)
    summaries: list[dict[str, Any]] = []

    for run_id, agg in sorted(runs.items()):
        rows = agg.rows
        latencies = [float(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None]
        token_speeds = [float(r["tokens_per_sec"]) for r in rows if r.get("tokens_per_sec") is not None]
        citation_precision_values = [
            float(r["citation_precision"]) for r in rows if r.get("citation_precision") is not None
        ]

        total = len(rows)
        passed = sum(1 for r in rows if bool(r.get("passed", False)))
        hallucinations = sum(1 for r in rows if bool(r.get("hallucination", False)))

        pass_series, tps_series = _build_time_series(rows)

        summary = {
            "run_id": run_id,
            "model": agg.model,
            "prompt_version": agg.prompt_version,
            "retrieval_configuration": agg.retrieval_configuration,
            "temperature": agg.temperature,
            "chunk_size": agg.chunk_size,
            "mean_latency_ms": float(mean(latencies)) if latencies else 0.0,
            "p50_latency_ms": _percentile(latencies, 0.50),
            "p95_latency_ms": _percentile(latencies, 0.95),
            "pass_rate": (passed / total) if total else 0.0,
            "hallucination_rate": (hallucinations / total) if total else 0.0,
            "citation_precision": float(mean(citation_precision_values)) if citation_precision_values else 0.0,
            "tokens_per_sec_avg": float(mean(token_speeds)) if token_speeds else 0.0,
            "latency_distribution": sorted(latencies),
            "pass_rate_over_time": pass_series,
            "tokens_per_sec_over_time": tps_series,
        }
        summaries.append(summary)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": summaries,
    }


def build_comparison(summary_payload: dict[str, Any]) -> dict[str, Any]:
    runs = summary_payload.get("runs", [])
    if len(runs) < 2:
        single = runs[0]["run_id"] if runs else "n/a"
        return {
            "baseline_run": single,
            "candidate_run": single,
            "improvement_pass_rate": 0.0,
            "latency_delta_ms": 0.0,
        }

    baseline, candidate = runs[0], runs[1]
    return {
        "baseline_run": baseline["run_id"],
        "candidate_run": candidate["run_id"],
        "improvement_pass_rate": float(candidate["pass_rate"] - baseline["pass_rate"]),
        "latency_delta_ms": float(candidate["p50_latency_ms"] - baseline["p50_latency_ms"]),
    }


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    summary = summarize_runs(ARTIFACTS_DIR)
    with SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    comparison = build_comparison(summary)
    with COMPARISON_PATH.open("w", encoding="utf-8") as handle:
        json.dump(comparison, handle, indent=2)

    print(f"Wrote summary: {SUMMARY_PATH}")
    print(f"Wrote comparison: {COMPARISON_PATH}")


if __name__ == "__main__":
    main()
