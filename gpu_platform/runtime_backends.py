from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .metrics import (
    record_platform_runtime_deployment,
    record_platform_runtime_selection,
    record_platform_runtime_validation_failure,
    record_platform_vllm_config_generated,
)

PLATFORM_RUNTIME_ARTIFACTS_DIR = Path("artifacts/platform_jobs")
RUNTIME_SELECTIONS_PATH = PLATFORM_RUNTIME_ARTIFACTS_DIR / "runtime_selections.jsonl"
RUNTIME_VALIDATION_RESULTS_PATH = PLATFORM_RUNTIME_ARTIFACTS_DIR / "runtime_validation_results.jsonl"
VLLM_RUNTIME_CONFIGS_PATH = PLATFORM_RUNTIME_ARTIFACTS_DIR / "vllm_runtime_configs.jsonl"
RUNTIME_DEPLOYMENTS_PATH = PLATFORM_RUNTIME_ARTIFACTS_DIR / "runtime_deployments.jsonl"

ALLOWED_DISTRIBUTED_EXECUTORS = {"mp", "ray", "external_launcher", "uni"}


class InferenceRuntime(ABC):
    name: str

    @abstractmethod
    def validate_runtime_config(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate_runtime_config(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def summarize_runtime_plan(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class MockRuntime(InferenceRuntime):
    name = "mock"

    def validate_runtime_config(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        return {"valid": True, "reason_codes": [], "runtime_name": self.name}

    def generate_runtime_config(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "runtime_name": self.name,
            "mode": "simulated",
            "workload_type": str(job_spec.get("workload_type", "inference")),
            "model": str(job_spec.get("model", "unknown-model")),
        }

    def summarize_runtime_plan(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "runtime_name": self.name,
            "plan": "Fallback simulated execution plan.",
            "reason": "configuration is unsupported or non-vLLM workload",
        }


class VLLMRuntime(InferenceRuntime):
    name = "vllm"

    def validate_runtime_config(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        reason_codes: list[str] = []
        workload_type = str(job_spec.get("workload_type", "inference"))
        model = str(job_spec.get("model", "") or "").strip()
        tp = int(job_spec.get("tensor_parallel", 1) or 1)
        pp = int(job_spec.get("pipeline_parallel", 1) or 1)
        dp = int(job_spec.get("data_parallel", 1) or 1)
        nnodes = int(job_spec.get("nnodes", 1) or 1)
        executor = str(job_spec.get("distributed_executor_backend", "mp") or "mp")
        replicas = int(job_spec.get("replicas", 1) or 1)
        gpu_per_replica = int(job_spec.get("gpu_per_replica", job_spec.get("gpu_count", 1)) or 1)
        requested_gpus = max(1, replicas * gpu_per_replica)

        if workload_type == "inference" and not model:
            reason_codes.append("missing_model")
        if tp < 1 or pp < 1:
            reason_codes.append("invalid_runtime_config")
        if nnodes < 1:
            reason_codes.append("invalid_runtime_config")
        if executor not in ALLOWED_DISTRIBUTED_EXECUTORS:
            reason_codes.append("invalid_distributed_executor")
        if tp * pp * dp > requested_gpus:
            reason_codes.append("inconsistent_parallelism")

        return {
            "valid": len(reason_codes) == 0,
            "reason_codes": sorted(set(reason_codes)),
            "runtime_name": self.name,
        }

    def generate_runtime_config(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": str(job_spec.get("model", "")),
            "served_model_name": str(job_spec.get("served_model_name", job_spec.get("model", ""))),
            "tensor_parallel_size": int(job_spec.get("tensor_parallel", 1) or 1),
            "pipeline_parallel_size": int(job_spec.get("pipeline_parallel", 1) or 1),
            "data_parallel_size": int(job_spec.get("data_parallel", 1) or 1),
            "max_model_len": int(job_spec.get("max_model_len", 4096) or 4096),
            "gpu_memory_utilization": float(job_spec.get("gpu_memory_utilization", 0.9) or 0.9),
            "distributed_executor_backend": str(job_spec.get("distributed_executor_backend", "mp") or "mp"),
            "nnodes": int(job_spec.get("nnodes", 1) or 1),
            "node_rank": int(job_spec.get("node_rank", 0) or 0),
            "kv_cache_policy": str(job_spec.get("kv_cache_policy", "reuse") or "reuse"),
            "priority_class": str(job_spec.get("priority_class", "balanced") or "balanced"),
            "gpu_pool": str(job_spec.get("gpu_pool", "shared_pool") or "shared_pool"),
            "runtime_name": self.name,
        }

    def summarize_runtime_plan(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "runtime_name": self.name,
            "plan": "Deploy vLLM-style serving runtime",
            "topology": {
                "tensor_parallel": int(job_spec.get("tensor_parallel", 1) or 1),
                "pipeline_parallel": int(job_spec.get("pipeline_parallel", 1) or 1),
                "data_parallel": int(job_spec.get("data_parallel", 1) or 1),
                "nnodes": int(job_spec.get("nnodes", 1) or 1),
            },
        }


class TritonRuntime(InferenceRuntime):
    name = "triton"

    def validate_runtime_config(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        return {"valid": False, "reason_codes": ["unsupported_runtime"], "runtime_name": self.name}

    def generate_runtime_config(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        return {"runtime_name": self.name, "status": "stub"}

    def summarize_runtime_plan(self, job_spec: dict[str, Any]) -> dict[str, Any]:
        return {"runtime_name": self.name, "plan": "stub-placeholder"}


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def _is_vllm_compatible(job_spec: dict[str, Any]) -> bool:
    return bool(str(job_spec.get("model", "")).strip()) and int(job_spec.get("gpu_count", 1) or 1) >= 1


def _make_vllm_deployment_config(job_spec: dict[str, Any], runtime_config: dict[str, Any], job_id: str) -> dict[str, Any]:
    model = runtime_config["model"]
    return {
        "job_id": job_id,
        "runtime_name": "vllm",
        "service_name": f"svc-{job_id}",
        "model": model,
        "container": {
            "image": str(job_spec.get("image", "vllm/vllm-openai:latest")),
            "args": [
                "--model", model,
                "--served-model-name", runtime_config["served_model_name"],
                "--tensor-parallel-size", str(runtime_config["tensor_parallel_size"]),
                "--pipeline-parallel-size", str(runtime_config["pipeline_parallel_size"]),
                "--max-model-len", str(runtime_config["max_model_len"]),
            ],
            "env": [
                {"name": "HF_TOKEN", "value": "${HF_TOKEN}"},
                {"name": "NCCL_DEBUG", "value": "${NCCL_DEBUG}"},
            ],
            "resources": {
                "requests": {"nvidia.com/gpu": str(job_spec.get("gpu_count", 1))},
                "limits": {"nvidia.com/gpu": str(job_spec.get("gpu_count", 1))},
            },
        },
        "readiness_probe": {"httpGet": {"path": "/health", "port": 8000}},
        "liveness_probe": {"httpGet": {"path": "/live", "port": 8000}},
    }


def plan_runtime(job_spec: dict[str, Any], job_id: str | None = None) -> dict[str, Any]:
    runtime_job_spec = dict(job_spec)
    runtime_job_spec.setdefault("nnodes", 1)
    workload_type = str(runtime_job_spec.get("workload_type", "inference"))
    priority_class = str(runtime_job_spec.get("priority_class", "balanced"))
    tp = int(runtime_job_spec.get("tensor_parallel", 1) or 1)
    pp = int(runtime_job_spec.get("pipeline_parallel", 1) or 1)

    use_vllm = False
    if workload_type == "inference" and priority_class == "latency-sensitive":
        use_vllm = True
    if tp > 1 or pp > 1:
        use_vllm = True
    if workload_type in {"batch", "eval"} and not _is_vllm_compatible(runtime_job_spec):
        use_vllm = False

    runtime: InferenceRuntime = VLLMRuntime() if use_vllm else MockRuntime()
    preferred_validation = runtime.validate_runtime_config(runtime_job_spec)
    fallback_from_vllm = False
    if not preferred_validation["valid"] and runtime.name == "vllm":
        runtime = MockRuntime()
        fallback_from_vllm = True

    selected_runtime = runtime.name
    validation_result = preferred_validation if fallback_from_vllm else runtime.validate_runtime_config(runtime_job_spec)
    runtime_plan = runtime.summarize_runtime_plan(runtime_job_spec)
    runtime_config = runtime.generate_runtime_config(runtime_job_spec)

    resolved_job_id = str(job_id or runtime_job_spec.get("job_id") or "unknown")

    selection_payload = {
        "job_id": resolved_job_id,
        "runtime_name": selected_runtime,
        "requested_runtime": "vllm" if use_vllm else "mock",
        "workload_type": workload_type,
        "priority_class": priority_class,
    }
    _append_jsonl(RUNTIME_SELECTIONS_PATH, selection_payload)
    record_platform_runtime_selection(selected_runtime)

    validation_payload = {
        "job_id": resolved_job_id,
        "runtime_name": selected_runtime,
        **validation_result,
    }
    _append_jsonl(RUNTIME_VALIDATION_RESULTS_PATH, validation_payload)
    for reason in validation_result.get("reason_codes", []):
        record_platform_runtime_validation_failure(reason)

    runtime_config_path: str | None = None
    deployment_config_path: str | None = None
    if selected_runtime == "vllm":
        vllm_payload = {"job_id": resolved_job_id, **runtime_config}
        _append_jsonl(VLLM_RUNTIME_CONFIGS_PATH, vllm_payload)
        record_platform_vllm_config_generated()
        runtime_config_path = str(VLLM_RUNTIME_CONFIGS_PATH)

        deployment_payload = _make_vllm_deployment_config(runtime_job_spec, runtime_config, resolved_job_id)
        _append_jsonl(RUNTIME_DEPLOYMENTS_PATH, deployment_payload)
        record_platform_runtime_deployment()
        deployment_config_path = str(RUNTIME_DEPLOYMENTS_PATH)

    return {
        "runtime_name": selected_runtime,
        "runtime_plan": runtime_plan,
        "runtime_config_path": runtime_config_path,
        "deployment_config_path": deployment_config_path,
        "validation": validation_result,
    }
