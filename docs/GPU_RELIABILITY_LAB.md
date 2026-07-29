# GPU Inference Reliability Lab

This prototype centers on bounded GPU-inference benchmark execution, provider adapters, routing and admission policies, telemetry normalization, and replayable evidence. It is implementation and deterministic-test evidence, not a production HPC deployment claim.

- Control-plane design: [GPU control-plane architecture](gpu-control-plane-architecture.md)
- Platform implementation: [`gpu_platform/`](../gpu_platform/)
- GPU-focused tests: [`tests/test_gpu_control_plane.py`](../tests/test_gpu_control_plane.py), [`tests/test_gpu_benchmark_runner.py`](../tests/test_gpu_benchmark_runner.py), and [`tests/test_gpu_optimization.py`](../tests/test_gpu_optimization.py)

Real-hardware performance remains `not_run` until an authenticated GPU benchmark completes.
