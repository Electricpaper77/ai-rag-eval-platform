from __future__ import annotations

import asyncio
import json
import sys
from urllib.parse import urlparse
from pathlib import Path

import yaml

import httpx

from backend.app.distributed import router as distributed_router_module
from backend.app.distributed.worker import WorkerRegistry


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class _Response:
    def __init__(self, status_code: int = 200, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}
        self.text = json.dumps(self._body)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._body


class _FakeClient:
    available = {"w1", "w2"}
    failing_posts: set[str] = set()
    reported_active: dict[str, int] = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    @staticmethod
    def _worker(url: str) -> str:
        return urlparse(url).hostname or "unknown"

    async def get(self, url: str):
        worker = self._worker(url.rsplit("/", 1)[0])
        if worker not in self.available:
            raise httpx.ConnectError("unavailable", request=None)
        if url.endswith("/healthz"):
            return _Response(body={"status": "ok", "worker_id": worker, "hostname": worker, "active_requests": self.reported_active.get(worker, 0)})
        return _Response(body={"status": "ready", "worker_id": worker})

    async def post(self, url: str, **kwargs):
        worker = self._worker(url.rsplit("/", 1)[0])
        if worker in self.failing_posts:
            raise httpx.ConnectError("failed", request=None)
        return _Response(body={"choices": [{"message": {"role": "assistant", "content": worker}}], "worker_id": worker})


def _registry() -> WorkerRegistry:
    registry = WorkerRegistry(["http://w1", "http://w2"], failure_threshold=1)
    for record in registry.records:
        record.metadata.health = "healthy"
        record.metadata.readiness = "ready"
        record.metadata.state = "healthy"
    return registry


def _install(monkeypatch, registry):
    monkeypatch.setattr(distributed_router_module, "registry", registry)
    monkeypatch.setattr(distributed_router_module.httpx, "AsyncClient", _FakeClient)
    _FakeClient.available = {"w1", "w2"}
    _FakeClient.failing_posts = set()
    _FakeClient.reported_active = {}


def test_round_robin_routes_to_both_workers(monkeypatch):
    registry = _registry()
    _install(monkeypatch, registry)

    async def run():
        return [await distributed_router_module.distributed_route({"policy": "round_robin"}) for _ in range(4)]

    results = asyncio.run(run())
    assert [result["selected_worker_id"] for result in results] == ["w1", "w2", "w1", "w2"]


def test_least_requests_prefers_less_busy_worker():
    registry = _registry()
    registry.records[0].metadata.active_requests = 3
    registry.records[1].metadata.active_requests = 0
    selected = registry.reserve(policy="least_requests")
    assert selected is not None
    assert selected.metadata.worker_id == "w2"


def test_real_http_forwarding_returns_routing_metadata(monkeypatch):
    registry = _registry()
    _install(monkeypatch, registry)

    result = asyncio.run(distributed_router_module.distributed_chat({"model": "mock", "messages": [{"role": "user", "content": "hi"}]}, "request-1"))
    assert result.status_code == 200
    body = json.loads(result.body)
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["distributed_routing"]["selected_worker_id"] in {"w1", "w2"}
    assert body["distributed_routing"]["request_id"] == "request-1"


def test_unhealthy_worker_is_excluded(monkeypatch):
    registry = _registry()
    _install(monkeypatch, registry)
    _FakeClient.available = {"w1"}

    result = asyncio.run(distributed_router_module.distributed_route({}))
    assert result["selected_worker_id"] == "w1"


def test_failed_worker_retries_once_on_alternate(monkeypatch):
    registry = _registry()
    registry._round_robin_index = 0
    _install(monkeypatch, registry)
    _FakeClient.failing_posts = {"w1"}

    result = asyncio.run(distributed_router_module.distributed_chat({"messages": [{"role": "user", "content": "retry"}]}, "retry-1"))
    assert result.status_code == 200
    body = json.loads(result.body)
    assert body["distributed_routing"]["selected_worker_id"] == "w2"
    assert body["distributed_routing"]["retry_count"] == 1
    assert body["distributed_routing"]["request_id"] == "retry-1"


def test_saturation_returns_structured_503(monkeypatch):
    registry = _registry()
    registry.max_inflight = 1
    _install(monkeypatch, registry)
    _FakeClient.reported_active = {"w1": 1, "w2": 1}

    result = asyncio.run(distributed_router_module.distributed_route({}))
    assert result.status_code == 503
    assert json.loads(result.body)["error"]["reason_code"] == "all_workers_saturated"


def test_no_worker_condition_is_structured(monkeypatch):
    registry = WorkerRegistry([])
    _install(monkeypatch, registry)
    result = asyncio.run(distributed_router_module.distributed_chat({"messages": [{"role": "user", "content": "none"}]}))
    assert result.status_code == 503
    assert json.loads(result.body)["error"]["reason_code"] == "no_healthy_worker"


def test_recovery_reintroduces_worker(monkeypatch):
    registry = _registry()
    _install(monkeypatch, registry)
    _FakeClient.available = {"w1"}
    asyncio.run(registry.refresh())
    assert registry.records[1].metadata.schedulable is False
    _FakeClient.available = {"w1", "w2"}
    asyncio.run(registry.refresh())
    assert registry.records[1].metadata.schedulable is True


def test_invalid_configuration_is_safe():
    registry = WorkerRegistry(["http://w1"], policy="unknown", max_inflight=0, queue_limit=-1)
    assert registry.policy == "round_robin"
    assert registry.max_inflight == 1
    assert registry.queue_limit == 0


def test_kubernetes_topology_has_two_secure_workers_and_restrictive_policies():
    documents = list(yaml.safe_load_all(Path("deploy/distributed/gate7.yaml").read_text(encoding="utf-8")))
    worker = next(item for item in documents if item.get("kind") == "Deployment" and item["metadata"]["name"] == "gate7-worker")
    assert worker["spec"]["replicas"] == 2
    for deployment in (worker, next(item for item in documents if item.get("kind") == "Deployment" and item["metadata"]["name"] == "gate7-router")):
        pod = deployment["spec"]["template"]
        assert pod["spec"]["automountServiceAccountToken"] is False
        assert pod["spec"]["securityContext"] == {
            "runAsNonRoot": True,
            "runAsUser": 10001,
            "runAsGroup": 10001,
            "seccompProfile": {"type": "RuntimeDefault"},
        }
        container = pod["spec"]["containers"][0]
        assert container["securityContext"]["readOnlyRootFilesystem"] is True
        assert container["securityContext"]["allowPrivilegeEscalation"] is False
        assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
        assert container["resources"]["requests"] and container["resources"]["limits"]
    policies = [item for item in documents if item.get("kind") == "NetworkPolicy"]
    assert len(policies) == 2
    assert all(policy["spec"]["policyTypes"] == ["Ingress", "Egress"] for policy in policies)
