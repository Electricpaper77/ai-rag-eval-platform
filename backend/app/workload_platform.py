"""Safe, local-first workload definitions for the AMD developer platform.

This module deliberately builds Kubernetes objects without contacting a cluster.
The execution adapter uses AgentTrust IQ's existing regression evaluator, making
local verification possible without claiming GPU or cloud execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .eval.regression import run_regression_eval

WORKLOAD_TYPES = {"dev-pod", "ci-job", "inference-service", "benchmark-job"}
router = APIRouter(prefix="/platform/workloads", tags=["workloads"])
DEFAULT_IMAGE = "python:3.11-slim"
SAFE_RESOURCES = {
    "requests": {"cpu": "250m", "memory": "512Mi"},
    "limits": {"cpu": "1", "memory": "1Gi"},
}


def _security_context() -> dict[str, Any]:
    return {
        "runAsNonRoot": True,
        "runAsUser": 10001,
        "runAsGroup": 10001,
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
        "seccompProfile": {"type": "RuntimeDefault"},
    }


def _container(name: str, image: str, command: list[str], port: int | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name, "image": image, "command": command,
        "resources": SAFE_RESOURCES,
        "securityContext": _security_context(),
        "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
    }
    if port:
        item["ports"] = [{"name": "http", "containerPort": port}]
    return item


def build_workload(name: str, workload_type: str, image: str = DEFAULT_IMAGE) -> list[dict[str, Any]]:
    if workload_type not in WORKLOAD_TYPES:
        raise ValueError(f"unsupported workload type: {workload_type}")
    labels = {"app.kubernetes.io/name": name, "app.kubernetes.io/part-of": "agenttrust-iq"}
    base = {"metadata": {"name": name, "labels": labels}}
    pod_meta = {"metadata": {"labels": labels}, "spec": {
        "restartPolicy": "Never", "automountServiceAccountToken": False,
        "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [], "volumes": [{"name": "tmp", "emptyDir": {}}],
    }}
    if workload_type == "dev-pod":
        pod_meta["spec"]["containers"] = [_container("dev", image, ["sleep", "3600"])]
        return [{"apiVersion": "v1", "kind": "Pod", **base, "spec": pod_meta["spec"]}]
    if workload_type == "ci-job":
        pod_meta["spec"]["containers"] = [_container("ci", image, ["python", "-m", "pytest", "-q"])]
        return [{"apiVersion": "batch/v1", "kind": "Job", **base,
                 "spec": {"backoffLimit": 1, "ttlSecondsAfterFinished": 300, "template": pod_meta}}]
    if workload_type == "benchmark-job":
        pod_meta["spec"]["containers"] = [_container("benchmark", image, ["python", "scripts/run_eval.py"])]
        return [{"apiVersion": "batch/v1", "kind": "Job", **base,
                 "spec": {"backoffLimit": 0, "ttlSecondsAfterFinished": 300, "template": pod_meta}}]
    pod_meta["spec"]["restartPolicy"] = "Always"
    pod_meta["spec"]["containers"] = [_container("inference", image, ["python", "-m", "http.server", "8080"], 8080)]
    deployment = {"apiVersion": "apps/v1", "kind": "Deployment", **base,
                  "spec": {"replicas": 1, "selector": {"matchLabels": labels}, "template": pod_meta}}
    service = {"apiVersion": "v1", "kind": "Service", **base,
               "spec": {"selector": labels, "ports": [{"port": 8080, "targetPort": 8080}]}}
    return [deployment, service]


def network_policy(name: str) -> dict[str, Any]:
    return {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {"name": name}, "spec": {"podSelector": {"matchLabels": {"app.kubernetes.io/name": name}},
            "policyTypes": ["Ingress", "Egress"], "ingress": [], "egress": []}}


@dataclass
class LocalWorkloadExecutor:
    root: Path
    query_fn: Callable[[str, int], dict[str, Any]]

    def run_benchmark(self, run_id: str | None = None) -> dict[str, Any]:
        return run_regression_eval(self.query_fn, run_id=run_id or uuid4().hex, artifact_dir=self.root)

    def cleanup(self, run_id: str) -> bool:
        path = self.root / f"regression_{run_id}.jsonl"
        if not path.exists():
            return False
        path.unlink()
        return not path.exists()


class WorkloadRequest(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    workload_type: str
    image: str = DEFAULT_IMAGE


@router.post("/manifest")
def workload_manifest(payload: WorkloadRequest) -> dict[str, Any]:
    """Return admission-safe objects; applying them remains an explicit operator action."""
    return {"name": payload.name, "workload_type": payload.workload_type,
            "objects": build_workload(payload.name, payload.workload_type, payload.image),
            "network_policy": network_policy(payload.name), "execution": "manifest-only"}
