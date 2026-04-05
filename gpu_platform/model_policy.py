from __future__ import annotations

from typing import Any

FAST_MODEL_CANDIDATES = ("mock", "vllm", "openai")
HIGH_QUALITY_MODEL_CANDIDATES = ("openai", "vllm", "mock")
BALANCED_MODEL_CANDIDATES = ("vllm", "openai", "mock")
FALLBACK_MODEL = "mock"


def _is_healthy(model_name: str, model_health_status: dict[str, str]) -> bool:
    status = str(model_health_status.get(model_name, "unknown")).lower()
    return status in {"healthy", "ok", "ready", "up"}


def _pick_first_healthy(candidates: tuple[str, ...], model_health_status: dict[str, str]) -> str:
    for candidate in candidates:
        if _is_healthy(candidate, model_health_status):
            return candidate
    return FALLBACK_MODEL


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
