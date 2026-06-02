from __future__ import annotations

import time

import pytest

from app.adapters.base import AdapterError, BackendConfig, MockLocalAdapter
from app.artifacts import ArtifactWriter
from app.models import ChatCompletionRequest
from app.reliability import CircuitBreaker
from app.router import RuntimeBackend


class FailingAdapter(MockLocalAdapter):
    async def complete(self, request: ChatCompletionRequest):
        raise AdapterError("synthetic failure")


def test_fallback_routing_uses_next_backend(client, chat_payload):
    app = client.app
    first = app.state.backends[0]
    first.adapter = FailingAdapter(first.config)

    response = client.post(
        "/v1/chat/completions",
        json={**chat_payload, "routing_policy": "fallback_on_error"},
    )

    assert response.status_code == 200
    assert response.json()["backend"] != first.config.name
    assert first.circuit_breaker.failures >= 1


def test_circuit_breaker_opens_and_resets():
    breaker = CircuitBreaker(failure_threshold=2, reset_seconds=0.01)
    breaker.record_failure()
    assert not breaker.is_open
    breaker.record_failure()
    assert breaker.is_open
    time.sleep(0.02)
    assert not breaker.is_open


def test_jsonl_artifact_writing(tmp_path):
    writer = ArtifactWriter(tmp_path)
    writer.append_jsonl("routing_decisions.jsonl", {"backend": "mock-local", "policy": "lowest_cost"})
    line = (tmp_path / "routing_decisions.jsonl").read_text(encoding="utf-8").strip()
    assert '"backend": "mock-local"' in line

