from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROOF_DIR = Path("artifacts/proof")
SUMMARY_PATH = PROOF_DIR / "vllm_benchmark_summary.json"


def load_vllm_benchmark_summary(summary_path: Path | None = None) -> dict[str, Any]:
    summary_path = summary_path or SUMMARY_PATH
    if not summary_path.exists():
        return {
            "model": "",
            "avg_tokens_per_sec": 0.0,
            "p95_latency_ms": 0.0,
            "avg_prefill_latency_ms": 0.0,
            "avg_decode_latency_ms": 0.0,
            "avg_request_latency_ms": 0.0,
            "num_requests": 0,
            "requests": [],
        }
    return json.loads(summary_path.read_text(encoding="utf-8"))
