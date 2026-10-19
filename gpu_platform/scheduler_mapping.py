"""Explicit, non-integrated GPU request mapping for Kubernetes and Slurm."""

from __future__ import annotations


MAX_GPU_COUNT = 8


def validate_gpu_count(count: int) -> int:
    if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > MAX_GPU_COUNT:
        raise ValueError(f"gpu_count must be an integer between 0 and {MAX_GPU_COUNT}")
    return count


def kubernetes_gpu_request(count: int, resource_key: str = "amd.com/gpu") -> dict[str, str]:
    """Return a Kubernetes limits fragment; zero means no GPU request."""

    validate_gpu_count(count)
    if not resource_key or "/" not in resource_key:
        raise ValueError("resource_key must be a qualified Kubernetes resource name")
    return {} if count == 0 else {resource_key: str(count)}


def slurm_gpu_request(count: int) -> list[str]:
    """Return the equivalent Slurm CLI fragment; zero means CPU-only."""

    validate_gpu_count(count)
    return [] if count == 0 else ["--gres", f"gpu:{count}"]


def scheduler_mapping(count: int, resource_key: str = "amd.com/gpu") -> dict[str, object]:
    """Describe equivalent requests without implying scheduler integration."""

    validate_gpu_count(count)
    return {
        "gpu_count": count,
        "kubernetes": kubernetes_gpu_request(count, resource_key),
        "slurm": slurm_gpu_request(count),
        "integrated": False,
    }
