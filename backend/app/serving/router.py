from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from prometheus_client import Counter, Gauge, Histogram

from .models import CanaryPhase, CanaryPolicy, ModelRecord
from .registry import ModelRegistry


SERVING_REQUESTS_TOTAL = Counter("gate8_serving_requests_total", "Serving requests", ["version", "runtime", "result"])
SERVING_LATENCY_SECONDS = Histogram("gate8_serving_latency_seconds", "Serving latency", ["version"])
CANARY_WEIGHT = Gauge("gate8_canary_weight", "Current canary traffic weight", ["version"])
ROLLOUT_PHASE = Gauge("gate8_rollout_phase", "Rollout phase", ["phase"])
ROLLBACKS_TOTAL = Counter("gate8_rollbacks_total", "Automatic and manual rollbacks")
PROMOTIONS_TOTAL = Counter("gate8_promotions_total", "Successful promotions")
POLICY_VIOLATIONS_TOTAL = Counter("gate8_policy_violations_total", "Canary policy violations")


@dataclass
class RouteResult:
    payload: dict[str, Any]
    record: ModelRecord
    selected_by_weight: bool
    fallback: bool = False


class CanaryController:
    def __init__(self, *, baseline_endpoint: str, candidate_endpoint: str, policy: CanaryPolicy | None = None) -> None:
        self.registry = ModelRegistry()
        self.policy = policy or CanaryPolicy(
            error_rate_delta=float(os.getenv("GATE8_POLICY_ERROR_DELTA", "0.01")),
            latency_ratio=float(os.getenv("GATE8_POLICY_LATENCY_RATIO", "1.25")),
            minimum_samples=int(os.getenv("GATE8_POLICY_MIN_SAMPLES", "3")),
        )
        self.baseline = self.registry.register(ModelRecord("agenttrust", "baseline", "mock", baseline_endpoint, rollout_state="baseline", traffic_weight=100, readiness="ready"))
        self.candidate = self.registry.register(ModelRecord("agenttrust", "candidate", "mock", candidate_endpoint, rollout_state="standby", traffic_weight=0, readiness="ready"))
        self.phase = CanaryPhase.IDLE
        self.rollout_number = 0
        self.rollback_count = 0
        self.promotion_count = 0
        self.policy_violation_count = 0
        self.last_policy_evaluation: dict[str, Any] = {"passed": True, "reasons": []}
        self._sync_metrics()

    def _sync_metrics(self) -> None:
        CANARY_WEIGHT.labels("baseline").set(self.baseline.traffic_weight)
        CANARY_WEIGHT.labels("candidate").set(self.candidate.traffic_weight)
        for phase in CanaryPhase:
            ROLLOUT_PHASE.labels(phase.value).set(1 if self.phase == phase else 0)

    def _reset_metrics(self) -> None:
        self.registry.clear_metrics()
        self.last_policy_evaluation = {"passed": True, "reasons": []}

    def _weighted_choice(self, request_id: str) -> tuple[ModelRecord, bool]:
        slot = int(hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:8], 16) % 100
        if self.candidate.traffic_weight and slot < self.candidate.traffic_weight:
            return self.candidate, True
        return self.baseline, False

    def _policy(self) -> dict[str, Any]:
        baseline = self.baseline
        candidate = self.candidate
        reasons: list[str] = []
        enough_samples = candidate.request_count >= self.policy.minimum_samples
        if not enough_samples:
            reasons.append(f"candidate sample count {candidate.request_count} < {self.policy.minimum_samples}")
        if candidate.error_rate > baseline.error_rate + self.policy.error_rate_delta:
            reasons.append("candidate error rate exceeds policy")
        if baseline.latency_p95_ms and candidate.latency_p95_ms > baseline.latency_p95_ms * self.policy.latency_ratio:
            reasons.append("candidate p95 latency exceeds policy")
        if not candidate.ready:
            reasons.append("candidate is not ready")
        result = {
            "passed": not reasons,
            "reasons": reasons,
            "baseline_error_rate": baseline.error_rate,
            "candidate_error_rate": candidate.error_rate,
            "baseline_p95_ms": baseline.latency_p95_ms,
            "candidate_p95_ms": candidate.latency_p95_ms,
            "policy": self.policy.as_dict(),
        }
        self.last_policy_evaluation = result
        return result

    async def _probe_readiness(self, record: ModelRecord) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(record.endpoint.rstrip("/") + "/readyz")
                record.readiness = "ready" if response.status_code == 200 else "not_ready"
        except httpx.HTTPError:
            record.readiness = "not_ready"
        return record.ready

    async def start(self) -> dict[str, Any]:
        self.phase = CanaryPhase.STARTING
        baseline_ready = await self._probe_readiness(self.baseline)
        candidate_ready = await self._probe_readiness(self.candidate)
        if not baseline_ready or not candidate_ready:
            self.phase = CanaryPhase.FAILED
            self.baseline.traffic_weight = 100
            self.candidate.traffic_weight = 0
            self._sync_metrics()
            raise HTTPException(status_code=409, detail="baseline and candidate must be ready before canary start")
        self._reset_metrics()
        self.rollout_number += 1
        self.phase = CanaryPhase.CANARY
        self._set_weights(95, 5)
        return self.status()

    def _set_weights(self, baseline: int, candidate: int) -> None:
        self.baseline.traffic_weight = baseline
        self.candidate.traffic_weight = candidate
        self._sync_metrics()

    async def route(self, request_body: dict[str, Any], request_id: str | None = None) -> RouteResult:
        request_id = request_id or str(request_body.get("request_id") or f"gate8-{time.time_ns()}")
        record, selected_by_weight = self._weighted_choice(request_id)
        if record is self.candidate and not await self._probe_readiness(record):
            record, selected_by_weight = self.baseline, False
            fallback = True
        else:
            fallback = False
        if not await self._probe_readiness(record):
            raise HTTPException(status_code=503, detail="no ready serving runtime")
        payload = dict(request_body)
        payload["request_id"] = request_id
        started = time.perf_counter()
        success = False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(record.endpoint.rstrip("/") + "/v1/chat/completions", json=payload, headers={"x-request-id": request_id})
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if response.status_code != 200:
                raise HTTPException(status_code=502, detail=f"{record.version} serving returned HTTP {response.status_code}")
            result = response.json()
            result["request_id"] = request_id
            result["serving"] = {"model_version": record.version, "runtime": record.runtime}
            result["canary_routing"] = {"phase": self.phase.value, "route_weight": record.traffic_weight, "selected_by_weight": selected_by_weight, "fallback": fallback}
            success = True
            return RouteResult(result, record, selected_by_weight, fallback)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"{record.version} serving request failed: {type(exc).__name__}") from exc
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            record.record(elapsed_ms, success)
            SERVING_REQUESTS_TOTAL.labels(record.version, record.runtime, "success" if success else "error").inc()
            SERVING_LATENCY_SECONDS.labels(record.version).observe(elapsed_ms / 1000.0)

    def promote(self) -> dict[str, Any]:
        if self.phase != CanaryPhase.CANARY:
            raise HTTPException(status_code=409, detail=f"cannot promote from {self.phase.value}")
        evaluation = self._policy()
        if not evaluation["passed"]:
            return self.rollback(reason="; ".join(evaluation["reasons"]))
        self.phase = CanaryPhase.PROMOTING
        if self.candidate.traffic_weight < 25:
            self.phase = CanaryPhase.CANARY
            self._set_weights(75, 25)
        else:
            self.phase = CanaryPhase.PROMOTED
            self._set_weights(0, 100)
            self.baseline.rollout_state = "standby"
            self.candidate.rollout_state = "promoted"
            self.promotion_count += 1
            PROMOTIONS_TOTAL.inc()
        return self.status()

    def rollback(self, reason: str = "manual rollback") -> dict[str, Any]:
        self.phase = CanaryPhase.ROLLING_BACK
        self._set_weights(100, 0)
        self.baseline.rollout_state = "baseline"
        self.candidate.rollout_state = "rolled_back"
        self.rollback_count += 1
        self.policy_violation_count += int(reason != "manual rollback")
        if reason != "manual rollback":
            POLICY_VIOLATIONS_TOTAL.inc()
        ROLLBACKS_TOTAL.inc()
        self.phase = CanaryPhase.ROLLED_BACK
        self.last_policy_evaluation = {**self.last_policy_evaluation, "passed": False, "reasons": [reason]}
        self._sync_metrics()
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "rollout_number": self.rollout_number,
            "baseline": self.baseline.as_dict(),
            "candidate": self.candidate.as_dict(),
            "weights": {"baseline": self.baseline.traffic_weight, "candidate": self.candidate.traffic_weight},
            "policy_evaluation": self.last_policy_evaluation,
            "rollback_count": self.rollback_count,
            "promotion_count": self.promotion_count,
            "policy_violation_count": self.policy_violation_count,
        }


def _default_controller() -> CanaryController:
    return CanaryController(
        baseline_endpoint=os.getenv("GATE8_BASELINE_ENDPOINT", "http://127.0.0.1:18081"),
        candidate_endpoint=os.getenv("GATE8_CANDIDATE_ENDPOINT", "http://127.0.0.1:18082"),
    )


controller = _default_controller()
router = APIRouter(prefix="/platform")


@router.get("/models")
async def models() -> dict[str, Any]:
    return {"models": controller.registry.snapshot()}


@router.get("/models/{model_name}")
async def model_status(model_name: str) -> dict[str, Any]:
    models = [record.as_dict() for record in controller.registry.all() if record.name == model_name]
    if not models:
        raise HTTPException(status_code=404, detail="model not found")
    return {"model": model_name, "versions": models}


@router.get("/serving/status")
async def serving_status() -> dict[str, Any]:
    return {"models": controller.registry.snapshot(), "runtimes": ["mock", "openai-compatible", "vllm", "tgi", "triton"]}


@router.get("/canary/status")
async def canary_status() -> dict[str, Any]:
    return controller.status()


@router.post("/canary/start")
async def canary_start() -> dict[str, Any]:
    return await controller.start()


@router.post("/canary/promote")
async def canary_promote() -> dict[str, Any]:
    return controller.promote()


@router.post("/canary/rollback")
async def canary_rollback() -> dict[str, Any]:
    return controller.rollback()


@router.post("/serving/chat")
async def serving_chat(request: dict[str, Any]) -> dict[str, Any]:
    result = await controller.route(request, request_id=request.get("request_id"))
    return result.payload
