from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any

FAST_MODEL_CANDIDATES = ("mock", "vllm", "openai")
HIGH_QUALITY_MODEL_CANDIDATES = ("openai", "vllm", "mock")
BALANCED_MODEL_CANDIDATES = ("vllm", "openai", "mock")
FALLBACK_MODEL = "mock"

MODEL_BENCHMARKS_PATH = Path("artifacts/model_benchmarks.json")
MODEL_SELECTION_DECISIONS_PATH = Path("artifacts/model_selection_decisions.jsonl")


def _is_healthy(model_name: str, model_health_status: dict[str, str]) -> bool:
    status = str(model_health_status.get(model_name, "unknown")).lower()
    return status in {"healthy", "ok", "ready", "up"}


def _pick_first_healthy(candidates: tuple[str, ...], model_health_status: dict[str, str]) -> str:
    for candidate in candidates:
        if _is_healthy(candidate, model_health_status):
            return candidate
    return FALLBACK_MODEL


def _load_model_benchmarks(path: Path | None = None) -> dict[str, dict[str, float]]:
    benchmark_path = path or MODEL_BENCHMARKS_PATH
    if not benchmark_path.exists():
        return {}

    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, dict[str, float]] = {}
    for model_name, metrics in payload.items():
        if not isinstance(metrics, dict):
            continue
        try:
            normalized[model_name] = {
                "p50_latency": float(metrics["p50_latency"]),
                "quality_score": float(metrics["quality_score"]),
                "cost_per_1k_tokens": float(metrics["cost_per_1k_tokens"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return normalized


def _normalize_inverse(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        return 1.0
    return max(0.0, min(1.0, (upper - value) / (upper - lower)))


def _quality_floor_for_tier(quality_tier: str) -> float:
    tier = quality_tier.strip().lower()
    if tier in {"premium", "high", "high_quality"}:
        return 0.88
    if tier in {"balanced", "medium", "standard"}:
        return 0.75
    return 0.0


def _record_selection_decision(decision: dict[str, Any], path: Path | None = None) -> None:
    output_path = path or MODEL_SELECTION_DECISIONS_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(decision) + "\n")


def select_model(latency_budget_ms: int, quality_tier: str, cost_budget: float) -> dict[str, Any]:
    """Select model with weighted score balancing latency, quality, and cost."""

    benchmarks = _load_model_benchmarks()
    if not benchmarks:
        decision = {
            "timestamp": time(),
            "latency_budget_ms": latency_budget_ms,
            "quality_tier": quality_tier,
            "cost_budget": cost_budget,
            "selected_model": FALLBACK_MODEL,
            "reason": "no_benchmarks",
            "score": 0.0,
        }
        _record_selection_decision(decision)
        return decision

    quality_floor = _quality_floor_for_tier(quality_tier)
    candidates = {
        model_name: metrics
        for model_name, metrics in benchmarks.items()
        if metrics["p50_latency"] <= latency_budget_ms
        and metrics["cost_per_1k_tokens"] <= cost_budget
        and metrics["quality_score"] >= quality_floor
    }
    if not candidates:
        candidates = benchmarks

    latencies = [m["p50_latency"] for m in candidates.values()]
    costs = [m["cost_per_1k_tokens"] for m in candidates.values()]
    min_latency, max_latency = min(latencies), max(latencies)
    min_cost, max_cost = min(costs), max(costs)

    scored_candidates: list[dict[str, Any]] = []
    for model_name, metrics in candidates.items():
        normalized_latency = _normalize_inverse(metrics["p50_latency"], min_latency, max_latency)
        cost_efficiency = _normalize_inverse(metrics["cost_per_1k_tokens"], min_cost, max_cost)
        score = (0.4 * normalized_latency) + (0.4 * metrics["quality_score"]) + (0.2 * cost_efficiency)
        scored_candidates.append(
            {
                "model": model_name,
                "normalized_latency": round(normalized_latency, 6),
                "quality_score": round(metrics["quality_score"], 6),
                "cost_efficiency": round(cost_efficiency, 6),
                "score": round(score, 6),
                "p50_latency": metrics["p50_latency"],
                "cost_per_1k_tokens": metrics["cost_per_1k_tokens"],
            }
        )

    selected = max(scored_candidates, key=lambda item: item["score"])
    decision = {
        "timestamp": time(),
        "latency_budget_ms": latency_budget_ms,
        "quality_tier": quality_tier,
        "cost_budget": cost_budget,
        "selected_model": selected["model"],
        "selected_score": selected["score"],
        "selected_latency_ms": selected["p50_latency"],
        "selected_cost_per_1k_tokens": selected["cost_per_1k_tokens"],
        "candidates": scored_candidates,
    }
    _record_selection_decision(decision)
    return decision


def select_model_by_policy(
    latency_budget_ms: int,
    quality_tier: str,
    cost_priority: str,
    model_health_status: dict[str, str],
) -> dict[str, Any]:
    """Choose a model route using simple platform-style policy signals."""

    tier = quality_tier.lower().strip()
    cost = cost_priority.lower().strip()

    if latency_budget_ms <= 700:
        preferred = FAST_MODEL_CANDIDATES
        reason = "Low latency budget; preferring fast-path models"
    elif tier in {"premium", "high", "quality"}:
        preferred = HIGH_QUALITY_MODEL_CANDIDATES
        reason = "Premium quality tier selected; preferring highest quality models"
    elif cost in {"high", "aggressive", "maximize"}:
        preferred = ("mock", "vllm", "openai")
        reason = "Cost-priority mode selected; preferring lower-cost models"
    else:
        preferred = BALANCED_MODEL_CANDIDATES
        reason = "Balanced routing policy selected"

    selected = _pick_first_healthy(preferred, model_health_status=model_health_status)
    if not _is_healthy(selected, model_health_status):
        selected = FALLBACK_MODEL
        reason = "Primary choices unhealthy; fallback model selected"

    return {
        "selected_model": selected,
        "routing_reason": reason,
    }
