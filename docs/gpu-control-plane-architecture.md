# GPU Control Plane Architecture

This platform adds a vendor-agnostic inference control plane that routes requests between:

- **NVIDIA Dynamo Triton-compatible runtime** (`nvidia_dynamo_triton`)
- **AMD ROCm vLLM-compatible runtime** (`amd_vllm_rocm`)

## Core components

- `backend/app/control_plane.py`
  - `/platform/route`: latency + quality tier + health based routing
  - `/platform/deployments/validate`: deployment compatibility validation
  - `/platform/status`: backend health, replica targets, artifact locations
- `backend/app/runtime_adapters/*.py`
  - RuntimeBackend-compatible adapter methods: `health_check`, `estimate_capacity`, `invoke_chat_completion`, `supported_hardware`
- `backend/app/autoscaling.py`
  - Simulated autoscaling policy from queue depth, p95 latency, utilization
- `backend/app/metrics_gpu_platform.py`
  - Prometheus metrics for request count, latency, throughput, queue depth, admission denials, autoscale recommendations

## Routing policy summary

1. Prefer NVIDIA for premium/high quality tier or strict latency budget.
2. Prefer AMD for cost/economy tier and healthy runtime.
3. Fall back to any healthy backend.
4. Enforce admission control using backend capacity estimate.

## Proof artifacts

- `artifacts/proof/routing_decisions.jsonl`
- `artifacts/proof/benchmark_runs.jsonl`
- `artifacts/proof/autoscaling_recommendations.jsonl`
- `artifacts/proof/admission_failures.jsonl`
