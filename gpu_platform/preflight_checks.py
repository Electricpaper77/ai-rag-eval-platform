from __future__ import annotations

from typing import Any

_REQUIRED_REASON_CODES = {
    "MISSING_IMAGE",
    "INVALID_GPU_COUNT",
    "MISSING_RESOURCE_LIMITS_REQUESTS",
    "MISSING_PROBES",
    "INVALID_STORAGE",
    "MISSING_NETWORK_POLICY_REF",
}


_TEMPLATE_GUARDS = {
    "inference": {
        "has_probes": True,
        "network_policy_ref": "k8s/templates/platform/network-policy-example.yaml",
    },
    "eval-batch": {
        "has_probes": True,
        "network_policy_ref": "k8s/templates/platform/network-policy-example.yaml",
    },
    "training": {
        "has_probes": True,
        "network_policy_ref": "k8s/templates/platform/network-policy-example.yaml",
    },
}


def run_preflight_checks(job_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []

    if not spec.get("image"):
        reason_codes.append("MISSING_IMAGE")

    if int(spec.get("gpu_count", 0) or 0) <= 0:
        reason_codes.append("INVALID_GPU_COUNT")

    cpu = str(spec.get("cpu", "")).strip()
    memory = str(spec.get("memory", "")).strip()
    if not cpu or not memory:
        reason_codes.append("MISSING_RESOURCE_LIMITS_REQUESTS")

    storage_class = str(spec.get("storage_class", "")).strip()
    pvc_size = str(spec.get("pvc_size", "")).strip()
    if not storage_class or not pvc_size:
        reason_codes.append("INVALID_STORAGE")

    workload_type = str(spec.get("workload_type", "")).strip().lower()
    template_guard = _TEMPLATE_GUARDS.get(workload_type)
    if not template_guard or not template_guard.get("has_probes"):
        reason_codes.append("MISSING_PROBES")

    if not template_guard or not template_guard.get("network_policy_ref"):
        reason_codes.append("MISSING_NETWORK_POLICY_REF")

    unknown_codes = sorted(set(reason_codes).difference(_REQUIRED_REASON_CODES))
    if unknown_codes:
        raise ValueError(f"Unexpected reason codes generated: {unknown_codes}")

    return {
        "job_id": job_id,
        "status": "pass" if not reason_codes else "fail",
        "reason_codes": reason_codes,
    }
