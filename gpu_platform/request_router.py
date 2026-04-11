from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter, time
from typing import Any

from gpu_platform.canary_controller import CANARY_CONTROLLER
from gpu_platform.metrics import (
    record_gpu_pool_selection,
    record_model_latency_seconds,
    record_model_request,
    record_model_selection_policy,
    record_kv_cache_strategy,
    record_routing_decision,
    record_routing_latency,
)
from gpu_platform.model_registry import load_model_registry
from gpu_platform.model_policy import select_model_by_policy
from gpu_platform.router_policies import rank_backends
from gpu_platform.shadow_eval import run_shadow_evaluation_async
from gpu_platform.job_status import log_job_run

ROUTING_DECISIONS_PATH = Path("artifacts/platform_jobs/routing_decisions.jsonl")
PREFIX_CACHE: set[str] = set()

_GPU_POOLS = {
    "latency_pool": {"capacity": 8, "runtime": "mock_vllm"},
    "throughput_pool": {"capacity": 24, "runtime": "mock_triton"},
    "distributed_pool": {"capacity": 16, "runtime": "mock_ray"},
    "shared_pool": {"capacity": 32, "runtime": "mock_vllm"},
}


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


def _choose_kv_cache_strategy(
    workload_type: str,
    parallelism_config: dict[str, Any],
    *,
    repeated_prompt: bool = False,
) -> str:
    if int(parallelism_config.get("context_tokens", 0) or 0) >= 4096:
        return "distributed"
    if repeated_prompt or bool(parallelism_config.get("repeat_prompt", False)):
        return "reuse"
    if workload_type == "batch":
        return "isolated"
    return "reuse"


def _choose_pool(
    workload_type: str,
    latency_budget_ms: int,
    priority_class: str,
    gpu_required: bool,
    parallelism_config: dict[str, Any],
    queue_depth: int,
    historical_failure_rate: float,
) -> tuple[str, str]:
    distributed_size = int(parallelism_config.get("data_parallel", 1) or 1) * int(
        parallelism_config.get("tensor_parallel", 1) or 1
    )
    if distributed_size >= 8:
        return "distributed_pool", "large_parallelism"
    if workload_type == "batch" or priority_class == "batch":
        return "throughput_pool", "batch_workload"
    if latency_budget_ms <= 900 or priority_class in {"latency-sensitive", "high"}:
        return "latency_pool", "latency_budget"
    if not gpu_required:
        return "shared_pool", "gpu_not_required"
    if queue_depth > 20 or historical_failure_rate >= 0.20:
        return "shared_pool", "resilience_fallback"
    return "throughput_pool", "balanced_default"


def _route_chat_request(
    messages: list[dict[str, Any]],
    latency_budget_ms: int,
    quality_tier: str,
    max_cost: float | None = None,
    *,
    request_id: str | None = None,
    force_shadow: bool | None = None,
) -> dict[str, Any]:
    req_id = request_id or hashlib.sha1(str(time()).encode("utf-8")).hexdigest()

    prefix = _get_prefix(messages)
    cache_hint_used = _is_repeated_prefix(prefix)

    model_registry = load_model_registry()
    policy_name = quality_tier if quality_tier in {"fast", "balanced", "high_quality"} else None

    if policy_name and model_registry:
        candidates = [
            model
            for model in model_registry
            if model["avg_latency_ms"] <= latency_budget_ms and (max_cost is None or model["cost_per_1k_tokens"] <= max_cost)
        ]
        if not candidates:
            candidates = [model for model in model_registry if max_cost is None or model["cost_per_1k_tokens"] <= max_cost]
        if not candidates:
            candidates = model_registry

        max_latency = max(model["avg_latency_ms"] for model in candidates) or 1.0
        max_cost_value = max(model["cost_per_1k_tokens"] for model in candidates) or 1.0
        enriched = []
        for model in candidates:
            latency_norm = model["avg_latency_ms"] / max_latency
            cost_norm = model["cost_per_1k_tokens"] / max_cost_value
            score = (
                (0.5 * model["quality_score"]) - (0.3 * latency_norm) - (0.2 * cost_norm)
                if policy_name == "balanced"
                else 0.0
            )
            enriched.append({**model, "score": score})

        if policy_name == "fast":
            selected_registry_model = min(enriched, key=lambda item: item["avg_latency_ms"])
        elif policy_name == "high_quality":
            selected_registry_model = max(enriched, key=lambda item: item["quality_score"])
        else:
            selected_registry_model = max(enriched, key=lambda item: item["score"])

        selected_backend = selected_registry_model["id"]
        selected_latency = _simulate_latency_ms(selected_registry_model["avg_latency_ms"], req_id, selected_backend)
        pass_outcome = _simulate_pass_outcome(selected_registry_model["quality_score"], req_id, selected_backend)
        hallucination_outcome = _simulate_hallucination_outcome(1.0 - selected_registry_model["quality_score"], req_id, selected_backend)
        primary_response = _simulate_model_response(selected_backend, messages)
        routing_reason = f"policy={policy_name}, provider={selected_registry_model['provider']}"
        record_model_selection_policy(policy_name)
        record_model_request(selected_backend)
        record_model_latency_seconds(selected_backend, selected_latency / 1000.0)

        decision_row = {
            "request_id": req_id,
            "selected_backend": selected_backend,
            "routing_score": selected_registry_model["score"],
            "cache_hint_used": cache_hint_used,
            "latency_budget_ms": latency_budget_ms,
            "quality_tier": quality_tier,
            "policy_selected_model": selected_backend,
            "routing_reason": routing_reason,
            "canary_applied": False,
            "rollback_triggered": False,
            "timestamp": time(),
        }
        _log_routing_decision(decision_row)

        log_job_run(
            job_id=req_id,
            model_used=selected_backend,
            latency_ms=selected_latency,
            success=pass_outcome,
        )
        return {
            "request_id": req_id,
            "selected_backend": selected_backend,
            "active_backend": selected_backend,
            "routing_score": selected_registry_model["score"],
            "routing_reason": routing_reason,
            "cache_hint_used": cache_hint_used,
            "canary_applied": False,
            "rollback_triggered": False,
            "response": primary_response,
            "policy": policy_name,
            "hallucination_outcome": hallucination_outcome,
        }

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


def route_request(
    workload_type: str | list[dict[str, Any]] | None = None,
    latency_budget_ms: int = 1500,
    priority_class: str = "balanced",
    max_cost: float | None = None,
    gpu_required: bool = True,
    parallelism_config: dict[str, Any] | None = None,
    request_id: str | None = None,
    queue_depth: int = 0,
    historical_failure_rate: float = 0.0,
    quality_tier: str | None = None,
    force_shadow: bool | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Route requests using either the new workload routing API or legacy chat routing shape."""
    if messages is not None:
        return _route_chat_request(
            messages=messages,
            latency_budget_ms=latency_budget_ms,
            quality_tier=quality_tier or priority_class,
            max_cost=max_cost,
            request_id=request_id,
            force_shadow=force_shadow,
        )

    if isinstance(workload_type, list):
        return _route_chat_request(
            messages=workload_type,
            latency_budget_ms=latency_budget_ms,
            quality_tier=quality_tier or priority_class,
            max_cost=max_cost,
            request_id=request_id,
            force_shadow=force_shadow,
        )

    workload_type = workload_type or "inference"

    started = perf_counter()
    cfg = parallelism_config or {}
    req_id = request_id or hashlib.sha1(f"{workload_type}:{time()}".encode("utf-8")).hexdigest()

    gpu_pool, routing_reason = _choose_pool(
        workload_type=workload_type,
        latency_budget_ms=latency_budget_ms,
        priority_class=priority_class,
        gpu_required=gpu_required,
        parallelism_config=cfg,
        queue_depth=queue_depth,
        historical_failure_rate=historical_failure_rate,
    )

    selected_runtime = _GPU_POOLS[gpu_pool]["runtime"]
    kv_cache_strategy = _choose_kv_cache_strategy(workload_type, cfg)
    batching_strategy = "dynamic" if gpu_pool in {"throughput_pool", "distributed_pool"} else "micro_batch"

    decision = {
        "request_id": req_id,
        "selected_runtime": selected_runtime,
        "runtime": selected_runtime,
        "gpu_pool": gpu_pool,
        "routing_reason": routing_reason,
        "kv_cache_strategy": kv_cache_strategy,
        "batching_strategy": batching_strategy,
        "queue_depth": queue_depth,
        "historical_failure_rate": historical_failure_rate,
        "pool_capacity": _GPU_POOLS[gpu_pool]["capacity"],
        "timestamp": time(),
    }

    _log_routing_decision(decision)

    latency = max((perf_counter() - started) * 1000.0, 0.01)
    record_routing_decision(workload_type=workload_type, priority_class=priority_class, runtime=selected_runtime)
    record_routing_latency(workload_type=workload_type, gpu_pool=gpu_pool, latency_ms=latency)
    record_kv_cache_strategy(strategy=kv_cache_strategy)
    record_gpu_pool_selection(gpu_pool=gpu_pool)

    return decision
