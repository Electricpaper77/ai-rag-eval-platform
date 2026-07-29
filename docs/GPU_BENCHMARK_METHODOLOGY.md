# GPU Benchmark Methodology

The repository's GPU benchmark scripts bound request execution and record structured artifacts. [`scripts/run_real_gpu_benchmark.py`](../scripts/run_real_gpu_benchmark.py) defaults to 50 requests; [`scripts/run_gpu_benchmark.py`](../scripts/run_gpu_benchmark.py) emits benchmark JSONL/summary artifacts; provider calls use explicit timeouts.

Fixture and mock comparisons are static demonstration data, not hardware benchmarks. A real-hardware result requires an authenticated endpoint and benchmark run; until then, hardware performance is `not_run`.

Relevant tests: [`tests/test_real_gpu_benchmark.py`](../tests/test_real_gpu_benchmark.py), [`tests/test_gpu_benchmark_runner.py`](../tests/test_gpu_benchmark_runner.py), and [`tests/test_gpu_optimization.py`](../tests/test_gpu_optimization.py).
