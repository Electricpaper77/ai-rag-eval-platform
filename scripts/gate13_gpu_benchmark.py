"""Bounded, no-fallback AMD ROCm benchmark used by Gate 13."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Sequence


def run_benchmark(*, warmups: int, iterations: int) -> dict[str, Any]:
    if warmups < 0 or iterations < 1:
        raise ValueError("warmups must be >= 0 and iterations must be >= 1")
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - hardware environment only
        raise RuntimeError(f"PyTorch is unavailable: {exc}") from exc
    if not getattr(getattr(torch, "version", None), "hip", None):
        raise RuntimeError("PyTorch HIP/ROCm build is required")
    if not torch.cuda.is_available():
        raise RuntimeError("no ROCm GPU is visible to PyTorch")

    device = torch.device("cuda:0")
    torch.manual_seed(13)
    left = torch.randn((1024, 1024), device=device)
    right = torch.randn((1024, 1024), device=device)
    for _ in range(warmups):
        _ = left @ right
    torch.cuda.synchronize(device)
    torch.cuda.reset_peak_memory_stats(device)
    latencies_ms: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        _ = left @ right
        torch.cuda.synchronize(device)
        latencies_ms.append((time.perf_counter() - started) * 1000)

    latencies_ms.sort()
    p50 = statistics.median(latencies_ms)
    p95_index = min(len(latencies_ms) - 1, max(0, int(len(latencies_ms) * 0.95) - 1))
    p95 = latencies_ms[p95_index]
    return {
        "status": "PASS",
        "device": str(device),
        "device_name": torch.cuda.get_device_name(device),
        "torch_hip_version": torch.version.hip,
        "warmups": warmups,
        "iterations": iterations,
        "p50_ms": p50,
        "p95_ms": p95,
        "throughput_ops_per_sec": 1000 / statistics.mean(latencies_ms),
        "peak_memory_allocated_bytes": torch.cuda.max_memory_allocated(device),
        "synchronized_each_iteration": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("artifacts/gate13/benchmark.json"))
    args = parser.parse_args(argv)
    try:
        result = run_benchmark(warmups=args.warmups, iterations=args.iterations)
    except Exception as exc:  # pragma: no cover - hardware environment only
        print(f"GPU_BENCHMARK: FAIL: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("GPU_BENCHMARK: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
