from __future__ import annotations

import re
from typing import Any, Dict, List

from .gpu_job import GPUJobSpec

_IMAGE_RE = re.compile(r"^[a-zA-Z0-9._/-]+(?::[a-zA-Z0-9._-]+)?$")


def run_preflight_checks(job: GPUJobSpec) -> Dict[str, Any]:
    errors: List[str] = []

    if job.gpu_count <= 0:
        errors.append("gpu_count must be greater than 0")

    if job.replicas <= 0:
        errors.append("replicas must be greater than 0")

    if not job.container_image or not _IMAGE_RE.match(job.container_image):
        errors.append("container_image must be a valid image reference")

    if not isinstance(job.resources, dict) or not job.resources:
        errors.append("resources must be a non-empty dict with limits")
    elif "limits" not in job.resources or not isinstance(job.resources.get("limits"), dict):
        errors.append("resources.limits must be present")

    if not isinstance(job.env, dict):
        errors.append("env must be a dict")

    return {
        "job_id": job.job_id,
        "status": "ok" if not errors else "fail",
        "errors": errors,
    }
