from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVAL_SUMMARY_PATH = Path("artifacts/proof/eval_dashboard_summary.json")
BEST_MODEL_PATH = Path("artifacts/platform_jobs/best_model.json")


def _normalize_latency(latency_ms: float, max_latency_ms: float) -> float:
    if max_latency_ms <= 0:
        return 0.0
    return latency_ms / max_latency_ms


def _compute_score(run: dict[str, Any], max_latency_ms: float) -> float:
    normalized_latency = _normalize_latency(float(run.get("p95_latency_ms", 0.0)), max_latency_ms)
    pass_rate = float(run.get("pass_rate", 0.0))
    hallucination_rate = float(run.get("hallucination_rate", 0.0))

    score = pass_rate * 0.5 - hallucination_rate * 0.3 - normalized_latency * 0.2
    return round(score, 4)


def select_best_model(eval_summary_path: Path | None = None) -> dict[str, Any]:
    summary_path = eval_summary_path or EVAL_SUMMARY_PATH
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    runs = payload.get("runs", [])
    if not runs:
        raise ValueError("No runs found in evaluation summary")

    max_latency_ms = max(float(run.get("p95_latency_ms", 0.0)) for run in runs)

    scored_runs: list[dict[str, Any]] = []
    for run in runs:
        scored_runs.append(
            {
                "run_id": run["run_id"],
                "score": _compute_score(run, max_latency_ms),
                "p95_latency_ms": float(run.get("p95_latency_ms", 0.0)),
                "pass_rate": float(run.get("pass_rate", 0.0)),
                "hallucination_rate": float(run.get("hallucination_rate", 0.0)),
                "tokens_per_sec_avg": float(run.get("tokens_per_sec_avg", 0.0)),
            }
        )

    best = max(scored_runs, key=lambda x: x["score"])
    result = {
        "selected_model": best["run_id"],
        "score": best["score"],
        "metrics": {
            "pass_rate": best["pass_rate"],
            "hallucination_rate": best["hallucination_rate"],
            "p95_latency_ms": best["p95_latency_ms"],
            "tokens_per_sec_avg": best["tokens_per_sec_avg"],
        },
    }

    BEST_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    BEST_MODEL_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result
