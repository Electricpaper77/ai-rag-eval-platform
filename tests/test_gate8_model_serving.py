from __future__ import annotations

import asyncio
import json
from urllib.parse import urlparse

import httpx
import pytest
import yaml
from fastapi import HTTPException

from backend.app.serving.adapters import AdapterConfig, TGIAdapter, TritonAdapter, adapter_for, validate_runtime_configs
from backend.app.serving.models import CanaryPhase, CanaryPolicy, ModelRecord
from backend.app.serving.registry import ModelRegistry
from backend.app.serving.router import CanaryController
import backend.app.serving.router as router_module


class _Response:
    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


class _Client:
    failing: set[str] = set()
    timeout = False

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url: str):
        version = urlparse(url).hostname or "unknown"
        if version in self.failing:
            return _Response(503, {"status": "unready"})
        return _Response(200, {"status": "ready", "version": version})

    async def post(self, url: str, **kwargs):
        version = urlparse(url).hostname or "unknown"
        if self.timeout:
            raise httpx.ReadTimeout("timed out", request=None)
        if version in self.failing:
            return _Response(503, {"detail": "forced failure"})
        return _Response(200, {"choices": [{"message": {"role": "assistant", "content": version}}]})


def _controller(monkeypatch) -> CanaryController:
    monkeypatch.setattr(router_module.httpx, "AsyncClient", _Client)
    _Client.failing = set()
    _Client.timeout = False
    return CanaryController(
        baseline_endpoint="http://baseline:8080",
        candidate_endpoint="http://candidate:8080",
        policy=CanaryPolicy(latency_ratio=10.0, minimum_samples=1),
    )


def test_runtime_adapters_validate_configs_and_payloads():
    statuses = validate_runtime_configs()
    assert {item["runtime"] for item in statuses} == {"vllm", "tgi", "triton"}
    assert all(item["status"] == "CONFIG_VALIDATED" for item in statuses)
    assert TGIAdapter(AdapterConfig("http://tgi:8080")).build_request([{"role": "user", "content": "hello"}])["inputs"] == "hello"
    assert TritonAdapter(AdapterConfig("http://triton:8000")).build_request([{"role": "user", "content": "hello"}])["inputs"][0]["name"] == "TEXT"
    with pytest.raises(ValueError):
        adapter_for("vllm", AdapterConfig("not-an-url"))


def test_model_registry_tracks_versions_and_clears_metrics():
    registry = ModelRegistry()
    record = registry.register(ModelRecord("agenttrust", "baseline", "mock", "http://baseline"))
    record.record(10, True)
    assert registry.get("agenttrust", "baseline") is record
    assert registry.snapshot()[0]["request_count"] == 1
    registry.clear_metrics()
    assert record.request_count == 0 and record.latency_p95_ms == 0


def test_weighted_routing_is_deterministic_and_distributed(monkeypatch):
    controller = _controller(monkeypatch)
    asyncio.run(controller.start())
    results = [asyncio.run(controller.route({"messages": [{"role": "user", "content": "x"}], "request_id": f"r-{i}"}, f"r-{i}")) for i in range(100)]
    candidate_count = sum(result.record.version == "candidate" for result in results)
    assert 1 <= candidate_count <= 15
    assert [result.record.version for result in results] == [asyncio.run(controller.route({"messages": [{"role": "user", "content": "x"}], "request_id": f"r-{i}"}, f"r-{i}")).record.version for i in range(100)]


def test_healthy_candidate_promotes_in_two_stages(monkeypatch):
    controller = _controller(monkeypatch)
    asyncio.run(controller.start())
    for i in range(30):
        asyncio.run(controller.route({"messages": [{"role": "user", "content": "x"}], "request_id": f"healthy-{i}"}, f"healthy-{i}"))
    first = controller.promote()
    assert first["phase"] == CanaryPhase.CANARY.value and first["weights"]["candidate"] == 25
    second = controller.promote()
    assert second["phase"] == CanaryPhase.PROMOTED.value and second["weights"]["candidate"] == 100


def test_policy_violation_rolls_back_candidate():
    controller = CanaryController(baseline_endpoint="http://baseline:8080", candidate_endpoint="http://candidate:8080")
    controller.phase = CanaryPhase.CANARY
    controller._set_weights(95, 5)
    for _ in range(10):
        controller.baseline.record(10, True)
        controller.candidate.record(100, True)
    result = controller.promote()
    assert result["phase"] == CanaryPhase.ROLLED_BACK.value
    assert result["weights"] == {"baseline": 100, "candidate": 0}
    assert result["policy_evaluation"]["passed"] is False


def test_manual_rollback_is_idempotent_and_restores_baseline():
    controller = CanaryController(baseline_endpoint="http://baseline:8080", candidate_endpoint="http://candidate:8080")
    controller.phase = CanaryPhase.PROMOTED
    controller._set_weights(0, 100)
    first = controller.rollback()
    second = controller.rollback()
    assert first["phase"] == second["phase"] == CanaryPhase.ROLLED_BACK.value
    assert second["weights"]["baseline"] == 100


def test_no_candidate_routes_to_baseline(monkeypatch):
    controller = _controller(monkeypatch)
    result = asyncio.run(controller.route({"messages": [{"role": "user", "content": "x"}], "request_id": "baseline-only"}, "baseline-only"))
    assert result.record.version == "baseline"


def test_unready_candidate_prevents_canary_start(monkeypatch):
    controller = _controller(monkeypatch)
    _Client.failing = {"candidate"}
    with pytest.raises(HTTPException):
        asyncio.run(controller.start())
    assert controller.phase == CanaryPhase.FAILED


def test_timeout_is_reported_as_serving_error(monkeypatch):
    controller = _controller(monkeypatch)
    _Client.timeout = True
    with pytest.raises(HTTPException) as error:
        asyncio.run(controller.route({"messages": [{"role": "user", "content": "x"}], "request_id": "timeout"}, "timeout"))
    assert error.value.status_code == 502


def test_request_id_is_preserved(monkeypatch):
    controller = _controller(monkeypatch)
    result = asyncio.run(controller.route({"messages": [{"role": "user", "content": "x"}], "request_id": "preserve-me"}, "preserve-me"))
    assert result.payload["request_id"] == "preserve-me"


def test_policy_manifest_has_progressive_stages():
    with open("deploy/canary/gate8-policy.yaml", encoding="utf-8") as handle:
        policy = yaml.safe_load(handle)
    assert policy["spec"]["stages"] == [5, 25, 100]
