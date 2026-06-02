from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVAL_SUMMARY_PATH = Path("artifacts/proof/eval_dashboard_summary.json")
DEFAULT_BACKEND_METRICS: dict[str, dict[str, float]] = {
    "vllm": {
        "pass_rate": 0.9,
        "hallucination_rate": 0.05,
        "p95_latency_ms": 800.0,
        "tokens_per_sec_avg": 75.0,
    },
    "openai": {
        "pass_rate": 0.92,
        "hallucination_rate": 0.04,
        "p95_latency_ms": 1100.0,
        "tokens_per_sec_avg": 55.0,
    },
    "mock": {
        "pass_rate": 0.7,
        "hallucination_rate": 0.2,
        "p95_latency_ms": 250.0,
        "tokens_per_sec_avg": 20.0,
    },
}

QUALITY_TIER_MULTIPLIERS: dict[str, dict[str, float]] = {
    "speed": {"latency": 1.2, "quality": 0.85},
    "balanced": {"latency": 1.0, "quality": 1.0},
    "quality": {"latency": 0.85, "quality": 1.15},
}


def _normalize(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return min(max(value / max_value, 0.0), 1.0)


def _map_run_to_backend(run_id: str) -> str | None:
    run_id_lower = run_id.lower()
    for backend in DEFAULT_BACKEND_METRICS:
        if backend in run_id_lower:
            return backend
    return None


def load_backend_metrics(eval_summary_path: Path | None = None) -> dict[str, dict[str, float]]:
    metrics = {key: value.copy() for key, value in DEFAULT_BACKEND_METRICS.items()}
    summary_path = eval_summary_path or EVAL_SUMMARY_PATH

    if not summary_path.exists():
        return metrics

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    runs = payload.get("runs", [])
    for run in runs:
        backend = _map_run_to_backend(str(run.get("run_id", "")))
        if backend is None:
            continue

        metrics[backend] = {
            "pass_rate": float(run.get("pass_rate", metrics[backend]["pass_rate"])),
            "hallucination_rate": float(run.get("hallucination_rate", metrics[backend]["hallucination_rate"])),
            "p95_latency_ms": float(run.get("p95_latency_ms", metrics[backend]["p95_latency_ms"])),
            "tokens_per_sec_avg": float(run.get("tokens_per_sec_avg", metrics[backend]["tokens_per_sec_avg"])),
        }

    return metrics


def score_backend(
    backend: str,
    metrics: dict[str, dict[str, float]],
    latency_budget_ms: int,
    quality_tier: str,
    vllm_bonus: float = 0.0,
) -> float:
    backend_metrics = metrics[backend]

    max_latency = max(values["p95_latency_ms"] for values in metrics.values())
    max_tps = max(values["tokens_per_sec_avg"] for values in metrics.values())

    normalized_latency = _normalize(backend_metrics["p95_latency_ms"], max_latency)
    normalized_tps = _normalize(backend_metrics["tokens_per_sec_avg"], max_tps)

    tier = QUALITY_TIER_MULTIPLIERS.get(quality_tier, QUALITY_TIER_MULTIPLIERS["balanced"])
    quality_weight = tier["quality"]
    latency_weight = tier["latency"]

    budget_penalty = 0.0
    if backend_metrics["p95_latency_ms"] > latency_budget_ms:
        budget_penalty = min((backend_metrics["p95_latency_ms"] - latency_budget_ms) / max(latency_budget_ms, 1), 1.0) * 0.2

    score = (
        backend_metrics["pass_rate"] * (0.45 * quality_weight)
        - backend_metrics["hallucination_rate"] * (0.25 * quality_weight)
        - normalized_latency * (0.20 * latency_weight)
        + normalized_tps * 0.10
        - budget_penalty
    )

    if backend == "vllm":
        score += vllm_bonus

    return round(score, 4)


def rank_backends(
    latency_budget_ms: int,
    quality_tier: str,
    cache_hint_used: bool,
    eval_summary_path: Path | None = None,
) -> list[dict[str, Any]]:
    metrics = load_backend_metrics(eval_summary_path=eval_summary_path)
    vllm_bonus = 0.10 if cache_hint_used else 0.0

    ranked = []
    for backend in ("vllm", "openai", "mock"):
        ranked.append(
            {
                "backend": backend,
                "score": score_backend(
                    backend=backend,
                    metrics=metrics,
                    latency_budget_ms=latency_budget_ms,
                    quality_tier=quality_tier,
                    vllm_bonus=vllm_bonus,
                ),
                "metrics": metrics[backend],
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked
