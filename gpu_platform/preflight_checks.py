from __future__ import annotations

from typing import Any

VALID_WORKLOAD_TYPES = {"inference", "batch-eval", "training"}
VALID_LIFECYCLE_STATES = {"queued", "admitted", "running", "succeeded", "failed"}


def _looks_like_image(image: str) -> bool:
    return "/" in image and ":" in image and len(image.strip()) > 3


def run_preflight_checks(job_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a platform job spec before admission."""
    reason_codes: list[str] = []

    if int(spec.get("gpu_count", 0) or 0) <= 0:
        reason_codes.append("invalid_gpu_request")

    if not str(spec.get("cpu", "")).strip() or not str(spec.get("memory", "")).strip():
        reason_codes.append("invalid_resource_limits")

    image = str(spec.get("image", "")).strip()
    if not _looks_like_image(image):
        reason_codes.append("invalid_container_image")

    retry_limit = int(spec.get("retry_limit", 0) or 0)
    if retry_limit < 0 or retry_limit > 10:
        reason_codes.append("invalid_retry_policy")

    if not str(spec.get("storage_class", "")).strip() or not str(spec.get("pvc_size", "")).strip() or not str(spec.get("mount_path", "")).strip():
        reason_codes.append("missing_storage_config")

    if not (spec.get("readiness_probe") and spec.get("liveness_probe")):
        reason_codes.append("invalid_probe_config")

    if not spec.get("network_isolation"):
        reason_codes.append("missing_network_isolation")

    replicas = int(spec.get("replicas", 1) or 1)
    tensor_parallel = int(spec.get("tensor_parallel", 1) or 1)
    pipeline_parallel = int(spec.get("pipeline_parallel", 1) or 1)
    gpu_per_replica = int(spec.get("gpu_per_replica", spec.get("gpu_count", 1)) or 1)
    if min(replicas, tensor_parallel, pipeline_parallel, gpu_per_replica) <= 0:
        reason_codes.append("invalid_parallelism_config")

    workload_type = str(spec.get("workload_type", "")).strip().lower()
    if workload_type not in VALID_WORKLOAD_TYPES:
        reason_codes.append("invalid_workload_type")

    return {
        "job_id": job_id,
        "status": "pass" if not reason_codes else "fail",
        "reason_codes": sorted(set(reason_codes)),
    }
