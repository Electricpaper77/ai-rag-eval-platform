from __future__ import annotations

"""Parallelism configuration abstraction for GPU inference simulations."""

from dataclasses import asdict, dataclass


@dataclass
class ParallelismConfig:
    tensor_parallel_size: int = 1
    pipeline_parallel_size: int = 1
    max_batch_tokens: int = 4096

    def __post_init__(self) -> None:
        if self.tensor_parallel_size < 1:
            raise ValueError("tensor_parallel_size must be >= 1")
        if self.pipeline_parallel_size < 1:
            raise ValueError("pipeline_parallel_size must be >= 1")
        if self.max_batch_tokens < 256:
            raise ValueError("max_batch_tokens must be >= 256")

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


EXAMPLE_PARALLELISM_CONFIG = {
    "tensor_parallel_size": 2,
    "pipeline_parallel_size": 1,
    "max_batch_tokens": 4096,
}


def estimate_gpu_memory_usage(model_size: str, parallelism_config: ParallelismConfig) -> dict[str, float]:
    """Estimate per-GPU memory footprint in GB for model+activation overhead.

    model_size supports shorthand like "7b", "13b", "70b".
    """

    compact = str(model_size).strip().lower().replace(" ", "")
    if compact.endswith("b"):
        params_b = float(compact[:-1])
    else:
        params_b = float(compact)

    total_params = params_b * 1_000_000_000
    bytes_per_param = 2.0  # bf16/fp16 simulation
    total_model_gb = (total_params * bytes_per_param) / (1024**3)

    shard_factor = parallelism_config.tensor_parallel_size * parallelism_config.pipeline_parallel_size
    model_shard_gb = total_model_gb / max(1, shard_factor)

    activation_overhead_gb = (parallelism_config.max_batch_tokens / 1024.0) * 0.75
    runtime_buffer_gb = 2.0

    per_gpu_memory_gb = round(model_shard_gb + activation_overhead_gb + runtime_buffer_gb, 2)
    return {
        "total_model_memory_gb": round(total_model_gb, 2),
        "per_gpu_memory_gb": per_gpu_memory_gb,
        "activation_overhead_gb": round(activation_overhead_gb, 2),
    }
