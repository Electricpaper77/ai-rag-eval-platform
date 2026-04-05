from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import time
from typing import Any

from gpu_platform.canary_controller import CANARY_CONTROLLER
from gpu_platform.router_policies import rank_backends
from gpu_platform.shadow_eval import record_shadow_result

ROUTING_DECISIONS_PATH = Path("artifacts/platform_jobs/routing_decisions.jsonl")
PREFIX_CACHE: set[str] = set()


def _get_prefix(messages: list[dict[str, Any]]) -> str:
    joined = "\n".join(str(msg.get("content", "")) for msg in messages[:2])
    return joined.strip()


def _is_repeated_prefix(prefix: str) -> bool:
    if not prefix:
        return False
    repeated = prefix in PREFIX_CACHE
    PREFIX_CACHE.add(prefix)
    return repeated


def _simulate_latency_ms(p95_latency_ms: float, request_id: str, backend: str) -> float:
    deterministic = int(hashlib.md5(f"{request_id}:{backend}".encode("utf-8")).hexdigest(), 16) % 200
    return round(max(p95_latency_ms * 0.8 + deterministic, 1.0), 2)


def _simulate_pass_outcome(pass_rate: float, request_id: str, backend: str) -> bool:
    deterministic = int(hashlib.sha1(f"pass:{request_id}:{backend}".encode("utf-8")).hexdigest(), 16) % 1000
    return (deterministic / 1000.0) < pass_rate


def _simulate_hallucination_outcome(hallucination_rate: float, request_id: str, backend: str) -> bool:
    deterministic = int(hashlib.sha1(f"hall:{request_id}:{backend}".encode("utf-8")).hexdigest(), 16) % 1000
    return (deterministic / 1000.0) < hallucination_rate


def _should_shadow(request_id: str) -> bool:
    return int(hashlib.sha1(request_id.encode("utf-8")).hexdigest(), 16) % 10 == 0


def _log_routing_decision(decision: dict[str, Any], log_path: Path | None = None) -> None:
    path = log_path or ROUTING_DECISIONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(decision) + "\n")


def route_request(
    messages: list[dict[str, Any]],
    latency_budget_ms: int,
    quality_tier: str,
    *,
    request_id: str | None = None,
    force_shadow: bool | None = None,
) -> dict[str, Any]:
    req_id = request_id or hashlib.sha1(str(time()).encode("utf-8")).hexdigest()

    prefix = _get_prefix(messages)
    cache_hint_used = _is_repeated_prefix(prefix)

    ranked = rank_backends(
        latency_budget_ms=latency_budget_ms,
        quality_tier=quality_tier,
        cache_hint_used=cache_hint_used,
    )

    ranked_by_backend = {item["backend"]: item for item in ranked}

    canary_applied, forced_backend, rollback_triggered = CANARY_CONTROLLER.choose_backend(req_id)
    if canary_applied and forced_backend in ranked_by_backend:
        selected = ranked_by_backend[forced_backend]
    else:
        selected = ranked[0]

    selected_latency = _simulate_latency_ms(selected["metrics"]["p95_latency_ms"], req_id, selected["backend"])
    pass_outcome = _simulate_pass_outcome(selected["metrics"]["pass_rate"], req_id, selected["backend"])
    hallucination_outcome = _simulate_hallucination_outcome(
        selected["metrics"]["hallucination_rate"], req_id, selected["backend"]
    )

    if canary_applied:
        CANARY_CONTROLLER.record_decision(
            request_id=req_id,
            active_backend=selected["backend"],
            latency_ms=selected_latency,
            pass_outcome=pass_outcome,
            hallucination_outcome=hallucination_outcome,
        )

    decision_row = {
        "request_id": req_id,
        "selected_backend": selected["backend"],
        "routing_score": selected["score"],
        "cache_hint_used": cache_hint_used,
        "latency_budget_ms": latency_budget_ms,
        "quality_tier": quality_tier,
        "canary_applied": canary_applied,
        "rollback_triggered": rollback_triggered,
        "timestamp": time(),
    }
    _log_routing_decision(decision_row)

    do_shadow = force_shadow if force_shadow is not None else _should_shadow(req_id)
    if do_shadow and len(ranked) > 1:
        shadow = ranked[1]
        shadow_result = {
            "request_id": req_id,
            "selected_backend": selected["backend"],
            "shadow_backend": shadow["backend"],
            "selected_latency_ms": selected_latency,
            "shadow_latency_ms": _simulate_latency_ms(shadow["metrics"]["p95_latency_ms"], req_id, shadow["backend"]),
            "selected_score": selected["score"],
            "shadow_score": shadow["score"],
        }
        record_shadow_result(shadow_result)

    latest_status = CANARY_CONTROLLER.status()
    return {
        "request_id": req_id,
        "selected_backend": selected["backend"],
        "active_backend": selected["backend"],
        "routing_score": selected["score"],
        "cache_hint_used": cache_hint_used,
        "canary_applied": canary_applied,
        "rollback_triggered": bool(latest_status.get("rollback_triggered", False)),
    }
