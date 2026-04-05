from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import time
from typing import Any

from gpu_platform.canary_controller import CANARY_CONTROLLER
from gpu_platform.router_policies import rank_backends
from gpu_platform.shadow_eval import run_shadow_evaluation_async
from gpu_platform.model_policy import select_model_by_policy
from gpu_platform.job_status import log_job_run

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


def _simulate_model_response(backend: str, messages: list[dict[str, Any]]) -> str:
    prompt = "\n".join(str(message.get("content", "")) for message in messages if message.get("content"))
    last_line = prompt.splitlines()[-1] if prompt else ""
    return f"[{backend}] {last_line[:120]}".strip()


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
    model_health_status = {backend: "healthy" for backend in ranked_by_backend}

    policy_decision = select_model_by_policy(
        latency_budget_ms=latency_budget_ms,
        quality_tier=quality_tier,
        cost_priority="balanced",
        model_health_status=model_health_status,
    )

    canary_applied, forced_backend, rollback_triggered = CANARY_CONTROLLER.choose_backend(req_id)
    if canary_applied and forced_backend in ranked_by_backend:
        selected = ranked_by_backend[forced_backend]
    elif policy_decision["selected_model"] in ranked_by_backend:
        selected = ranked_by_backend[policy_decision["selected_model"]]
    else:
        selected = ranked[0]

    selected_latency = _simulate_latency_ms(selected["metrics"]["p95_latency_ms"], req_id, selected["backend"])
    pass_outcome = _simulate_pass_outcome(selected["metrics"]["pass_rate"], req_id, selected["backend"])
    hallucination_outcome = _simulate_hallucination_outcome(
        selected["metrics"]["hallucination_rate"], req_id, selected["backend"]
    )
    primary_response = _simulate_model_response(selected["backend"], messages)

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
        "policy_selected_model": policy_decision["selected_model"],
        "routing_reason": policy_decision["routing_reason"],
        "canary_applied": canary_applied,
        "rollback_triggered": rollback_triggered,
        "timestamp": time(),
    }
    _log_routing_decision(decision_row)

    do_shadow = bool(force_shadow) or quality_tier == "balanced"
    if do_shadow and len(ranked) > 1:
        shadow = ranked[1]
        shadow_latency = _simulate_latency_ms(shadow["metrics"]["p95_latency_ms"], req_id, shadow["backend"])
        run_shadow_evaluation_async(
            request_id=req_id,
            primary_model=selected["backend"],
            shadow_model=shadow["backend"],
            messages=messages,
            primary_response=primary_response,
            primary_latency_ms=selected_latency,
            shadow_latency_ms=shadow_latency,
        )

    log_job_run(
        job_id=req_id,
        model_used=selected["backend"],
        latency_ms=selected_latency,
        success=pass_outcome,
    )

    latest_status = CANARY_CONTROLLER.status()
    return {
        "request_id": req_id,
        "selected_backend": selected["backend"],
        "active_backend": selected["backend"],
        "routing_score": selected["score"],
        "routing_reason": policy_decision["routing_reason"],
        "cache_hint_used": cache_hint_used,
        "canary_applied": canary_applied,
        "rollback_triggered": bool(latest_status.get("rollback_triggered", False)),
        "response": primary_response,
    }
