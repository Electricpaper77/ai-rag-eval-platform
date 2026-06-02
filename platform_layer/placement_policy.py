from __future__ import annotations


def choose_gpu_tier(latency_budget_ms: int, quality_tier: str, runtime: str) -> dict[str, str]:
    quality = quality_tier.lower().strip()
    runtime_name = runtime.lower().strip()

    if latency_budget_ms <= 400:
        gpu_tier = "premium"
        reason = "strict latency SLO requires highest-throughput tier"
    elif quality in {"high", "max", "best"}:
        gpu_tier = "premium"
        reason = "high quality tier mapped to premium GPU pool"
    elif runtime_name in {"triton", "vllm"} and latency_budget_ms <= 1200:
        gpu_tier = "standard"
        reason = "balanced latency tier"
    else:
        gpu_tier = "economy"
        reason = "cost-oriented tier for flexible latency workloads"

    return {
        "gpu_tier": gpu_tier,
        "placement_mode": "nodeSelector+toleration",
        "reason": reason,
    }


def build_k8s_placement_spec(job_type: str, gpu_tier: str) -> dict[str, object]:
    workload = "inference" if job_type.lower().strip() == "inference" else "batch"
    placement_mode = "nodeAffinity+toleration" if workload == "batch" else "nodeSelector+toleration"

    return {
        "job_type": workload,
        "gpu_tier": gpu_tier,
        "placement_mode": placement_mode,
        "labels": {
            "workload-type": workload,
            "gpu-tier": gpu_tier,
            "platform": "ai-eval",
        },
        "node_selector": {
            "gpu-tier": gpu_tier,
            "platform": "ai-eval",
        },
        "tolerations": [
            {
                "key": "nvidia.com/gpu",
                "operator": "Equal",
                "value": "present",
                "effect": "NoSchedule",
            }
        ],
    }


def explain_placement_reason(
    latency_budget_ms: int,
    quality_tier: str,
    runtime: str,
    job_type: str,
    gpu_tier: str,
) -> dict[str, str]:
    workload = job_type.lower().strip()
    explanation = (
        f"{workload} workload mapped to {gpu_tier} tier for runtime={runtime}, "
        f"quality_tier={quality_tier}, latency_budget_ms={latency_budget_ms}"
    )

    return {
        "gpu_tier": gpu_tier,
        "placement_mode": "nodeSelector+toleration" if workload == "inference" else "nodeAffinity+toleration",
        "reason": explanation,
    }
