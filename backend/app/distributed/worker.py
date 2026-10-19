from __future__ import annotations

import asyncio
import os
import socket
import time
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urlparse

import httpx

from .metrics import WORKER_ACTIVE_REQUESTS, WORKER_FAILURES_TOTAL, WORKER_HEALTH
from .models import WorkerMetadata, utc_now


def _split_urls(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


@dataclass
class _WorkerRecord:
    metadata: WorkerMetadata
    endpoint_key: str
    failure_threshold: int = 2
    lock: asyncio.Lock | None = None


class WorkerRegistry:
    """Health-aware worker registry with DNS discovery and bounded probes."""

    def __init__(
        self,
        endpoints: Iterable[str] = (),
        *,
        discovery_host: str | None = None,
        discovery_port: int = 8080,
        policy: str = "round_robin",
        max_inflight: int = 8,
        queue_limit: int = 0,
        probe_timeout: float = 1.0,
        failure_threshold: int = 2,
        resolver: Callable[[str, int], list[str]] | None = None,
    ) -> None:
        self.discovery_host = discovery_host or ""
        self.discovery_port = int(discovery_port)
        self.policy = policy if policy in {"round_robin", "least_requests"} else "round_robin"
        self.max_inflight = max(1, int(max_inflight))
        self.queue_limit = max(0, int(queue_limit))
        self.probe_timeout = max(0.1, float(probe_timeout))
        self.failure_threshold = max(1, int(failure_threshold))
        self._resolver = resolver or self._resolve_host
        self._records: dict[str, _WorkerRecord] = {}
        self._round_robin_index = 0
        self._refresh_lock = asyncio.Lock()
        for endpoint in endpoints:
            self._add_endpoint(endpoint)

    @classmethod
    def from_env(cls) -> "WorkerRegistry":
        return cls(
            _split_urls(os.getenv("GATE7_WORKER_URLS", "")),
            discovery_host=os.getenv("GATE7_WORKER_DISCOVERY_HOST", ""),
            discovery_port=int(os.getenv("GATE7_WORKER_DISCOVERY_PORT", "8080")),
            policy=os.getenv("GATE7_ROUTING_POLICY", "round_robin"),
            max_inflight=int(os.getenv("GATE7_MAX_INFLIGHT_PER_WORKER", "8")),
            queue_limit=int(os.getenv("GATE7_QUEUE_LIMIT", "0")),
            probe_timeout=float(os.getenv("GATE7_HEALTH_TIMEOUT_SECONDS", "1.0")),
            failure_threshold=int(os.getenv("GATE7_HEALTH_FAILURE_THRESHOLD", "2")),
        )

    @staticmethod
    def _resolve_host(host: str, port: int) -> list[str]:
        addresses = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
        return sorted({f"http://{item[4][0]}:{port}" for item in addresses})

    @staticmethod
    def _initial_worker_id(endpoint: str) -> str:
        parsed = urlparse(endpoint)
        return parsed.hostname or endpoint.rsplit("/", 1)[-1]

    def _add_endpoint(self, endpoint: str) -> _WorkerRecord:
        endpoint = endpoint.rstrip("/")
        existing = self._records.get(endpoint)
        if existing:
            return existing
        record = _WorkerRecord(
            metadata=WorkerMetadata(
                worker_id=self._initial_worker_id(endpoint),
                hostname=urlparse(endpoint).hostname or endpoint,
                endpoint=endpoint,
            ),
            endpoint_key=endpoint,
            failure_threshold=self.failure_threshold,
        )
        self._records[endpoint] = record
        return record

    def _discover_endpoints(self) -> list[str]:
        endpoints = list(self._records)
        if self.discovery_host:
            try:
                endpoints.extend(self._resolver(self.discovery_host, self.discovery_port))
            except OSError:
                pass
        return sorted(set(endpoint.rstrip("/") for endpoint in endpoints))

    async def refresh(self) -> list[WorkerMetadata]:
        async with self._refresh_lock:
            for endpoint in self._discover_endpoints():
                self._add_endpoint(endpoint)
            records = list(self._records.values())
            if records:
                await asyncio.gather(*(self._probe(record) for record in records))
            self._set_health_metrics()
            return self.list_workers()

    async def _probe(self, record: _WorkerRecord) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.probe_timeout) as client:
                health_response = await client.get(f"{record.metadata.endpoint}/healthz")
                ready_response = await client.get(f"{record.metadata.endpoint}/readyz")
            health_response.raise_for_status()
            ready_response.raise_for_status()
            health = health_response.json()
            ready = ready_response.json()
            record.metadata.worker_id = str(health.get("worker_id") or record.metadata.worker_id)
            record.metadata.hostname = str(health.get("hostname") or record.metadata.hostname)
            record.metadata.accelerator_type = str(health.get("accelerator_type", "cpu"))
            record.metadata.accelerator_count = int(health.get("accelerator_count", 0))
            record.metadata.active_requests = int(health.get("active_requests", record.metadata.active_requests))
            record.metadata.total_requests = int(health.get("total_requests", record.metadata.total_requests))
            record.metadata.failed_requests = int(health.get("failed_requests", record.metadata.failed_requests))
            record.metadata.health = "healthy"
            record.metadata.readiness = "ready" if ready.get("status") == "ready" else "not_ready"
            record.metadata.state = "healthy" if record.metadata.readiness == "ready" else "recovering"
            record.metadata.consecutive_failures = 0
            record.metadata.last_error = None
            record.metadata.last_heartbeat = utc_now()
        except Exception as exc:
            record.metadata.consecutive_failures += 1
            record.metadata.last_error = type(exc).__name__
            record.metadata.last_heartbeat = utc_now()
            record.metadata.health = "unhealthy" if record.metadata.consecutive_failures >= record.failure_threshold else "recovering"
            record.metadata.readiness = "not_ready"
            record.metadata.state = record.metadata.health
            WORKER_FAILURES_TOTAL.labels(record.metadata.worker_id, "health_probe").inc()

    def list_workers(self) -> list[WorkerMetadata]:
        return [record.metadata for record in sorted(self._records.values(), key=lambda item: item.endpoint_key)]

    def healthy_workers(self, exclude: set[str] | None = None) -> list[_WorkerRecord]:
        excluded = exclude or set()
        return [
            record
            for record in self._records.values()
            if record.metadata.schedulable and record.metadata.worker_id not in excluded
        ]

    def reserve(self, *, policy: str | None = None, exclude: set[str] | None = None) -> _WorkerRecord | None:
        candidates = [record for record in self.healthy_workers(exclude) if record.metadata.active_requests < self.max_inflight]
        if not candidates:
            return None
        selected_policy = policy or self.policy
        if selected_policy == "least_requests":
            selected = min(candidates, key=lambda record: (record.metadata.active_requests, record.metadata.total_requests, record.metadata.worker_id))
        else:
            candidates.sort(key=lambda record: record.metadata.worker_id)
            selected = candidates[self._round_robin_index % len(candidates)]
            self._round_robin_index += 1
        selected.metadata.active_requests += 1
        selected.metadata.total_requests += 1
        self._set_health_metrics()
        return selected

    def release(self, record: _WorkerRecord, *, success: bool) -> None:
        record.metadata.active_requests = max(0, record.metadata.active_requests - 1)
        if not success:
            record.metadata.failed_requests += 1
            record.metadata.health = "recovering"
            record.metadata.state = "recovering"
            record.metadata.readiness = "not_ready"
            record.metadata.consecutive_failures = max(1, record.metadata.consecutive_failures)
            WORKER_FAILURES_TOTAL.labels(record.metadata.worker_id, "request").inc()
        self._set_health_metrics()

    def _set_health_metrics(self) -> None:
        for record in self._records.values():
            WORKER_HEALTH.labels(record.metadata.worker_id).set(1 if record.metadata.schedulable else 0)
            WORKER_ACTIVE_REQUESTS.labels(record.metadata.worker_id).set(record.metadata.active_requests)

    def summary(self) -> dict:
        workers = self.list_workers()
        return {
            "policy": self.policy,
            "worker_count": len(workers),
            "healthy_count": sum(worker.schedulable for worker in workers),
            "max_inflight_per_worker": self.max_inflight,
            "queue_limit": self.queue_limit,
            "workers": [worker.as_dict() for worker in workers],
        }

    def mark_connection_failure(self, record: _WorkerRecord, error: Exception) -> None:
        record.metadata.failed_requests += 1
        record.metadata.consecutive_failures += 1
        record.metadata.last_error = type(error).__name__
        record.metadata.health = "unhealthy" if record.metadata.consecutive_failures >= record.failure_threshold else "recovering"
        record.metadata.state = record.metadata.health
        record.metadata.readiness = "not_ready"
        WORKER_FAILURES_TOTAL.labels(record.metadata.worker_id, "connection").inc()
        self._set_health_metrics()

    @property
    def records(self) -> list[_WorkerRecord]:
        return list(self._records.values())
