from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4
import re
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from .eval.regression import run_regression_eval

WORKLOAD_TYPES = ("dev-pod", "ci-job", "inference-service", "benchmark-job")
DEFAULT_IMAGE = "agenttrust-iq:ci"
MAX_GPU, MAX_REPLICAS, MAX_TTL = 8, 8, 86400
router = APIRouter(prefix="/platform/workloads", tags=["workloads"])

class AdmissionError(ValueError):
    def __init__(self, reasons: list[str]): self.reasons = reasons; super().__init__(", ".join(reasons))

class WorkloadRequest(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9]([-a-z0-9]{0,38}[a-z0-9])?$")
    workload_type: str
    image: str = DEFAULT_IMAGE
    cpu_request: str = "250m"; cpu_limit: str = "1"
    memory_request: str = "512Mi"; memory_limit: str = "1Gi"
    gpu_count: int = Field(default=0, ge=0, le=MAX_GPU)
    gpu_resource_key: str = Field(default="amd.com/gpu", pattern=r"^[a-z0-9.-]+/[a-z0-9.-]+$")
    node_selector: dict[str, str] = Field(default_factory=dict)
    tolerations: list[dict[str, Any]] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    command: list[str] | None = None; args: list[str] | None = None
    replicas: int = Field(default=1, ge=1, le=MAX_REPLICAS)
    pvc_size: str | None = None; storage_class: str | None = None
    mount_path: str = "/mnt/agenttrust"; priority_class: str | None = None
    ttl_seconds_after_finished: int = Field(default=300, ge=1, le=MAX_TTL)
    @field_validator("image")
    @classmethod
    def valid_image(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./:_-]{0,127}", value): raise ValueError("invalid_image")
        return value

def _security_context() -> dict[str, Any]:
    return {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001, "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}, "seccompProfile": {"type": "RuntimeDefault"}}

def _validate(request: WorkloadRequest) -> WorkloadRequest:
    reasons: list[str] = []
    if request.workload_type not in WORKLOAD_TYPES: reasons.append("unsupported_workload_type")
    if not all((request.cpu_request, request.cpu_limit, request.memory_request, request.memory_limit)): reasons.append("resource_limit_required")
    if request.mount_path == "/" or not request.mount_path.startswith("/"): reasons.append("invalid_mount_path")
    if request.command and any(x in {"sh", "bash", "cmd", "powershell"} for x in request.command): reasons.append("invalid_command")
    if request.pvc_size and not re.fullmatch(r"[1-9][0-9]*(Mi|Gi|Ti)", request.pvc_size): reasons.append("invalid_storage_request")
    if reasons: raise AdmissionError(reasons)
    return request

def _container(request: WorkloadRequest, name: str, command: list[str], port: int | None = None) -> dict[str, Any]:
    resources = {"requests": {"cpu": request.cpu_request, "memory": request.memory_request}, "limits": {"cpu": request.cpu_limit, "memory": request.memory_limit}}
    if request.gpu_count: resources["limits"][request.gpu_resource_key] = str(request.gpu_count)
    result: dict[str, Any] = {"name": name, "image": request.image, "command": command, "resources": resources,
        "securityContext": _security_context(), "env": [{"name": k, "value": v} for k, v in sorted(request.env.items())],
        "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}]}
    if request.pvc_size: result["volumeMounts"].append({"name": "workdir", "mountPath": request.mount_path})
    if port: result["ports"] = [{"name": "http", "containerPort": port}]
    return result

def _pod_spec(request: WorkloadRequest, container: dict[str, Any], restart: str = "Never") -> dict[str, Any]:
    spec: dict[str, Any] = {"restartPolicy": restart, "automountServiceAccountToken": False,
        "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001, "seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [container], "volumes": [{"name": "tmp", "emptyDir": {}}]}
    if request.pvc_size: spec["volumes"].append({"name": "workdir", "persistentVolumeClaim": {"claimName": request.name}})
    if request.node_selector: spec["nodeSelector"] = dict(sorted(request.node_selector.items()))
    if request.tolerations: spec["tolerations"] = request.tolerations
    if request.priority_class: spec["priorityClassName"] = request.priority_class
    return spec

def build_workload_request(request: WorkloadRequest) -> list[dict[str, Any]]:
    request = _validate(request); labels = {"app.kubernetes.io/name": request.name, "app.kubernetes.io/part-of": "agenttrust-iq"}
    base = {"metadata": {"name": request.name, "labels": labels}}
    commands = {"dev-pod": ["python", "-m", "scripts.gate1_inference"], "ci-job": ["python", "-m", "pytest", "-q", "tests/test_workload_platform.py"], "benchmark-job": ["python", "-m", "backend.app.eval.regression"], "inference-service": ["python", "-m", "scripts.gate1_inference"]}
    command = request.command or commands[request.workload_type]; container = _container(request, request.workload_type, command, 8080 if request.workload_type == "inference-service" else None)
    if request.args: container["args"] = request.args
    if request.workload_type == "inference-service":
        container["readinessProbe"] = {"httpGet": {"path": "/healthz", "port": 8080}, "periodSeconds": 5}; container["livenessProbe"] = {"httpGet": {"path": "/healthz", "port": 8080}, "periodSeconds": 10}
        objects = [{"apiVersion": "apps/v1", "kind": "Deployment", **base, "spec": {"replicas": request.replicas, "selector": {"matchLabels": labels}, "template": {"metadata": {"labels": labels}, "spec": _pod_spec(request, container, "Always")}}}, {"apiVersion": "v1", "kind": "Service", **base, "spec": {"selector": labels, "ports": [{"port": 8080, "targetPort": 8080}]}}]
    elif request.workload_type == "dev-pod": objects = [{"apiVersion": "v1", "kind": "Pod", **base, "spec": _pod_spec(request, container)}]
    else: objects = [{"apiVersion": "batch/v1", "kind": "Job", **base, "spec": {"backoffLimit": 1, "ttlSecondsAfterFinished": request.ttl_seconds_after_finished, "template": {"metadata": {"labels": labels}, "spec": _pod_spec(request, container)}}}]
    if request.pvc_size:
        pvc = {"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": request.name}, "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": request.pvc_size}}}}
        if request.storage_class: pvc["spec"]["storageClassName"] = request.storage_class
        objects.insert(0, pvc)
    return objects

def build_workload(name: str, workload_type: str, image: str = DEFAULT_IMAGE) -> list[dict[str, Any]]:
    return build_workload_request(WorkloadRequest(name=name, workload_type=workload_type, image=image))

def network_policy(name: str) -> dict[str, Any]:
    return {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": f"{name}-default-deny"}, "spec": {"podSelector": {"matchLabels": {"app.kubernetes.io/name": name}}, "policyTypes": ["Ingress", "Egress"], "ingress": [{"from": [{"podSelector": {"matchLabels": {"app.kubernetes.io/part-of": "agenttrust-iq"}}}]}], "egress": [{"ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}]}}

@dataclass
class LocalWorkloadExecutor:
    root: Path; query_fn: Callable[[str, int], dict[str, Any]]
    def run_benchmark(self, run_id: str | None = None) -> dict[str, Any]: return run_regression_eval(self.query_fn, run_id=run_id or uuid4().hex, artifact_dir=self.root)
    def cleanup(self, run_id: str) -> bool:
        path = self.root / f"regression_{run_id}.jsonl"
        if not path.exists(): return False
        path.unlink(); return not path.exists()

@router.get("/types")
def workload_types() -> dict[str, Any]: return {"workload_types": list(WORKLOAD_TYPES), "execution": "manifest-only"}

@router.post("/validate")
def validate_workload(payload: WorkloadRequest) -> dict[str, Any]:
    try: normalized = _validate(payload)
    except AdmissionError as exc: return {"admission_decision": "deny", "reason_codes": exc.reasons, "normalized_request": payload.model_dump()}
    return {"admission_decision": "allow", "reason_codes": [], "normalized_request": normalized.model_dump()}

@router.post("/manifest")
def workload_manifest(payload: WorkloadRequest) -> dict[str, Any]:
    normalized = _validate(payload)
    return {"admission_decision": "allow", "reason_codes": [], "name": normalized.name, "workload_type": normalized.workload_type, "objects": build_workload_request(normalized), "network_policy": network_policy(normalized.name), "execution": "manifest-only", "artifact_location": "/tmp/eval_runs" if normalized.workload_type == "benchmark-job" else None}
