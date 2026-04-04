#!/usr/bin/env python3
"""Simulate GPU inference benchmark metrics for a vLLM-like runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path
from statistics import mean
from typing import Any

DEFAULT_CONFIG_PATH = Path("configs/vllm_gpu_config.yaml")
DEFAULT_SUMMARY_PATH = Path("artifacts/proof/vllm_benchmark_summary.json")
DEFAULT_PROMPTS = [
    "Summarize GPU batch scheduling in one sentence.",
    "Explain how continuous batching improves throughput.",
    "What are trade-offs between low latency and high throughput?",
    "Give one best practice for serving Mistral-7B in production.",
    "Describe prefill vs decode phases for LLM inference.",
]


def _parse_simple_yaml(path: Path) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed_value: Any = value.strip()
        if parsed_value.isdigit():
            parsed_value = int(parsed_value)
        else:
            try:
                parsed_value = float(parsed_value)
            except ValueError:
                parsed_value = parsed_value
        config[key.strip()] = parsed_value
    return config


def _model_factor(model_name: str) -> float:
    compact = model_name.split("/")[-1].lower()
    return 1.0 + (sum(ord(ch) for ch in compact) % 11) / 20.0


def simulate_request_metrics(prompt: str, model: str, max_model_len: int, tensor_parallel_size: int) -> dict[str, float]:
    prompt_tokens = max(8, min(max_model_len // 8, len(prompt.split()) * 5))
    generated_tokens = max(24, min(256, int(prompt_tokens * 0.9)))

    model_factor = _model_factor(model)
    tp_factor = max(1, tensor_parallel_size)

    prefill_latency_ms = (0.65 * prompt_tokens + 12.0) / model_factor
    decode_latency_ms = (8.5 * generated_tokens) / (model_factor * tp_factor)
    request_latency_ms = prefill_latency_ms + decode_latency_ms
    tokens_per_sec = generated_tokens / (request_latency_ms / 1000)

    return {
        "prompt": prompt,
        "prompt_tokens": prompt_tokens,
        "generated_tokens": generated_tokens,
        "prefill_latency_ms": round(prefill_latency_ms, 2),
        "decode_latency_ms": round(decode_latency_ms, 2),
        "request_latency_ms": round(request_latency_ms, 2),
        "tokens_per_sec": round(tokens_per_sec, 2),
    }


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = int(round((pct / 100) * (len(sorted_values) - 1)))
    return sorted_values[index]


def run_vllm_benchmark(
    config_path: Path = DEFAULT_CONFIG_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    prompts: list[str] | None = None,
) -> dict[str, Any]:
    config = _parse_simple_yaml(config_path)
    model = str(config.get("model", "mistralai/Mistral-7B-Instruct-v0.2"))
    max_model_len = int(config.get("max_model_len", 4096))
    tensor_parallel_size = int(config.get("tensor_parallel_size", 1))

    active_prompts = prompts or DEFAULT_PROMPTS
    request_metrics = [
        simulate_request_metrics(
            prompt=prompt,
            model=model,
            max_model_len=max_model_len,
            tensor_parallel_size=tensor_parallel_size,
        )
        for prompt in active_prompts
    ]

    request_latencies = sorted(float(row["request_latency_ms"]) for row in request_metrics)

    summary = {
        "model": model,
        "max_model_len": max_model_len,
        "tensor_parallel_size": tensor_parallel_size,
        "num_requests": len(request_metrics),
        "avg_tokens_per_sec": round(mean(float(row["tokens_per_sec"]) for row in request_metrics), 2),
        "p95_latency_ms": round(percentile(request_latencies, 95), 2),
        "avg_prefill_latency_ms": round(mean(float(row["prefill_latency_ms"]) for row in request_metrics), 2),
        "avg_decode_latency_ms": round(mean(float(row["decode_latency_ms"]) for row in request_metrics), 2),
        "avg_request_latency_ms": round(mean(float(row["request_latency_ms"]) for row in request_metrics), 2),
        "requests": request_metrics,
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    config_path = Path(os.getenv("VLLM_GPU_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
    summary_path = Path(os.getenv("VLLM_BENCHMARK_SUMMARY_PATH", str(DEFAULT_SUMMARY_PATH)))

    summary = run_vllm_benchmark(config_path=config_path, summary_path=summary_path)
    print(json.dumps(summary, indent=2))
    print(f"Wrote vLLM benchmark summary to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
