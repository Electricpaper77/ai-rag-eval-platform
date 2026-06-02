from __future__ import annotations

import pytest

from app.adapters.base import BackendConfig, MockLocalAdapter
from app.benchmark import BenchmarkRecorder, sample_record
from app.models import ChatCompletionRequest
from app.reliability import CircuitBreaker
from app.router import InferenceRouter, RuntimeBackend


def backend(name: str, cost: float, quality: float, latency: float, weight: int = 1) -> RuntimeBackend:
    config = BackendConfig(
        name=name,
        adapter="mock",
        model_aliases=["gpt-4o-mini"],
        cost_per_1k_tokens=cost,
        quality_score=quality,
        expected_latency_ms=latency,
        weight=weight,
    )
    return RuntimeBackend(config=config, adapter=MockLocalAdapter(config), circuit_breaker=CircuitBreaker())


@pytest.fixture()
def chat_request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hello"}],
    )


def test_router_selects_lowest_cost(chat_request):
    chat_request.routing_policy = "lowest_cost"
    router = InferenceRouter(
        [backend("expensive", 0.5, 0.99, 10), backend("cheap", 0.1, 0.6, 100)],
        BenchmarkRecorder(),
    )
    assert router.candidates(chat_request)[0].config.name == "cheap"


def test_router_selects_highest_quality(chat_request):
    chat_request.routing_policy = "highest_quality"
    router = InferenceRouter(
        [backend("base", 0.1, 0.6, 10), backend("premium", 0.5, 0.99, 100)],
        BenchmarkRecorder(),
    )
    assert router.candidates(chat_request)[0].config.name == "premium"


def test_router_uses_observed_latency(chat_request):
    chat_request.routing_policy = "lowest_latency"
    recorder = BenchmarkRecorder()
    recorder.record(sample_record("slow-default", "lowest_latency", 20, 20, 0.001))
    router = InferenceRouter(
        [backend("slow-default", 0.1, 0.6, 300), backend("fast-default", 0.2, 0.7, 100)],
        recorder,
    )
    assert router.candidates(chat_request)[0].config.name == "slow-default"


def test_weighted_round_robin_visits_weighted_backends(chat_request):
    chat_request.routing_policy = "weighted_round_robin"
    router = InferenceRouter(
        [backend("small", 0.1, 0.6, 10, weight=1), backend("large", 0.2, 0.7, 10, weight=3)],
        BenchmarkRecorder(),
    )
    selections = [router.candidates(chat_request)[0].config.name for _ in range(8)]
    assert selections.count("large") > selections.count("small")
