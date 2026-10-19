"""Minimal in-cluster queue scaler with narrowly scoped Kubernetes RBAC."""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.request


NAMESPACE = os.getenv("GATE9_NAMESPACE", "gate9-capacity")
TARGET = os.getenv("GATE9_TARGET_DEPLOYMENT", "gate9-serving")
MIN_REPLICAS = int(os.getenv("GATE9_MIN_REPLICAS", "1"))
MAX_REPLICAS = int(os.getenv("GATE9_MAX_REPLICAS", "4"))
SERVICE_URL = os.getenv("GATE9_SERVICE_URL", "http://gate9-serving:8080")
API_SERVER = "https://kubernetes.default.svc"
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"


def _request(url: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    token = open(TOKEN_PATH, encoding="utf-8").read().strip()
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, method=method, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/strategic-merge-patch+json"})
    context = ssl.create_default_context(cafile=CA_PATH)
    with urllib.request.urlopen(request, context=context, timeout=5) as response:
        data = response.read().decode()
        return json.loads(data) if data else {}


def _recommendation() -> dict:
    with urllib.request.urlopen(f"{SERVICE_URL}/platform/capacity/recommendation", timeout=3) as response:
        return json.loads(response.read())


def _scale(replicas: int) -> None:
    _request(f"{API_SERVER}/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{TARGET}", method="PATCH", payload={"spec": {"replicas": replicas}})
    print(json.dumps({"queue_scaler": "scaled", "replicas": replicas}), flush=True)


def _current_replicas() -> int:
    deployment = _request(f"{API_SERVER}/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{TARGET}")
    return int(deployment.get("spec", {}).get("replicas", MIN_REPLICAS))


def main() -> None:
    interval = max(1, int(os.getenv("GATE9_QUEUE_SCALER_INTERVAL_SECONDS", "2")))
    while True:
        try:
            recommendation = _recommendation()
            action = recommendation.get("recommendation")
            current = _current_replicas()
            if action in {"scale_up", "capacity_exhausted"}:
                _scale(min(MAX_REPLICAS, current + 1))
            elif action == "scale_down" and current > MIN_REPLICAS:
                _scale(max(MIN_REPLICAS, current - 1))
        except Exception as exc:
            print(json.dumps({"queue_scaler": "poll_error", "error": type(exc).__name__}), flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
