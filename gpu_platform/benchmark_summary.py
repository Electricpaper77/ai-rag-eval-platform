from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROOF_DIR = Path("artifacts/proof")
SUMMARY_PATH = PROOF_DIR / "distributed_benchmark_summary.json"


REQUIRED_KEYS = {"run_id", "model", "gpu_count", "batch_size", "p95_latency_ms", "tokens_per_sec"}


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def aggregate_distributed_runs(proof_dir: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    proof_dir = proof_dir or PROOF_DIR
    candidates = sorted(proof_dir.glob("*.jsonl"))
    by_run: dict[str, dict[str, Any]] = {}

    for jsonl_path in candidates:
        for row in _read_jsonl_rows(jsonl_path):
            if not REQUIRED_KEYS.issubset(row):
                continue
            run_id = str(row["run_id"])
            by_run[run_id] = {
                "run_id": run_id,
                "model": row["model"],
                "gpu_count": int(row["gpu_count"]),
                "batch_size": int(row["batch_size"]),
                "p95_latency_ms": float(row["p95_latency_ms"]),
                "tokens_per_sec": float(row["tokens_per_sec"]),
            }

    runs = sorted(by_run.values(), key=lambda run: run["run_id"])
    return {"runs": runs}


def write_distributed_summary(
    summary: dict[str, list[dict[str, Any]]], summary_path: Path | None = None
) -> Path:
    summary_path = summary_path or SUMMARY_PATH
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary_path


def load_distributed_summary(
    summary_path: Path | None = None, proof_dir: Path | None = None
) -> dict[str, Any]:
    summary_path = summary_path or SUMMARY_PATH
    proof_dir = proof_dir or PROOF_DIR
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))

    summary = aggregate_distributed_runs(proof_dir=proof_dir)
    write_distributed_summary(summary, summary_path=summary_path)
    return summary
