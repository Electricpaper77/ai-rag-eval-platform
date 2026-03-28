#!/usr/bin/env python3
"""Compare two or more evaluation run JSONL files and print a markdown table.

The script reads evaluation rows from JSONL files, computes aggregate metrics, and
emits a comparison table that is suitable for CLI output, CI logs, or downstream
integration in a dashboard layer.

Computed metrics per run:
- p50 latency (ms)
- p95 latency (ms)
- average tokens/sec
- pass rate (%)

Supported input fields (row-level, best-effort):
- Latency: ``latency_ms``
- Pass flag: ``eval_pass`` / ``pass`` / ``passed``
- Throughput:
  - preferred: ``tokens_per_second``
  - fallback: ``tokens_generated`` divided by ``latency_ms``

Example:
    python scripts/compare_eval_runs.py \
      --run-a artifacts/evals/run_a.jsonl \
      --run-b artifacts/evals/run_b.jsonl

Optional (additional runs):
    python scripts/compare_eval_runs.py \
      --run-a artifacts/evals/run_a.jsonl \
      --run-b artifacts/evals/run_b.jsonl \
      --run artifacts/evals/run_c.jsonl
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np


PASS_KEYS: tuple[str, ...] = ("eval_pass", "pass", "passed")


@dataclass(frozen=True)
class RunMetrics:
    """Aggregate metrics for a single evaluation run."""

    run_label: str
    p50_latency_ms: float
    p95_latency_ms: float
    avg_tokens_per_second: float
    pass_rate_percent: float
    total_rows: int


@dataclass
class RunAccumulator:
    """Mutable accumulator used while scanning one JSONL run file."""

    latencies_ms: list[float]
    tokens_per_second: list[float]
    pass_count: int
    total_count: int

    def __init__(self) -> None:
        self.latencies_ms = []
        self.tokens_per_second = []
        self.pass_count = 0
        self.total_count = 0


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "passed"}
    return False


def _extract_pass_value(row: dict[str, object]) -> bool:
    for key in PASS_KEYS:
        if key in row:
            return _to_bool(row.get(key))
    return False


def _extract_tokens_per_second(row: dict[str, object]) -> float | None:
    direct = row.get("tokens_per_second")
    if direct is not None:
        try:
            value = float(direct)
            return value if value >= 0 else None
        except (TypeError, ValueError):
            return None

    tokens_generated = row.get("tokens_generated")
    latency_ms = row.get("latency_ms")
    try:
        tokens = float(tokens_generated)
        latency = float(latency_ms)
    except (TypeError, ValueError):
        return None

    if latency <= 0:
        return None
    return tokens / (latency / 1000.0)


def _extract_latency_ms(row: dict[str, object]) -> float | None:
    latency = row.get("latency_ms")
    try:
        value = float(latency)
        return value if value >= 0 else None
    except (TypeError, ValueError):
        return None


def load_run_metrics(run_path: Path, run_label: str | None = None) -> RunMetrics:
    """Load one JSONL run and compute aggregate metrics."""

    acc = RunAccumulator()

    with run_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {run_path}:{line_number}: {exc}") from exc

            if not isinstance(row, dict):
                raise ValueError(f"Expected object JSON at {run_path}:{line_number}, got {type(row).__name__}")

            acc.total_count += 1

            latency_ms = _extract_latency_ms(row)
            if latency_ms is not None:
                acc.latencies_ms.append(latency_ms)

            tps = _extract_tokens_per_second(row)
            if tps is not None:
                acc.tokens_per_second.append(tps)

            if _extract_pass_value(row):
                acc.pass_count += 1

    if acc.total_count == 0:
        raise ValueError(f"No evaluation rows found in {run_path}")

    p50 = float(np.percentile(acc.latencies_ms, 50)) if acc.latencies_ms else 0.0
    p95 = float(np.percentile(acc.latencies_ms, 95)) if acc.latencies_ms else 0.0
    avg_tps = float(np.mean(acc.tokens_per_second)) if acc.tokens_per_second else 0.0
    pass_rate = (acc.pass_count / acc.total_count) * 100.0

    return RunMetrics(
        run_label=run_label or run_path.stem,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        avg_tokens_per_second=avg_tps,
        pass_rate_percent=pass_rate,
        total_rows=acc.total_count,
    )


def render_markdown_table(metrics: Sequence[RunMetrics]) -> str:
    """Render run metrics as a markdown table."""

    header = (
        "| Run | Rows | p50 latency (ms) | p95 latency (ms) | "
        "Avg tokens/sec | Pass rate (%) |"
    )
    divider = "|---|---:|---:|---:|---:|---:|"

    lines = [header, divider]
    for item in metrics:
        lines.append(
            "| {run} | {rows} | {p50:.2f} | {p95:.2f} | {tps:.2f} | {pass_rate:.2f} |".format(
                run=item.run_label,
                rows=item.total_rows,
                p50=item.p50_latency_ms,
                p95=item.p95_latency_ms,
                tps=item.avg_tokens_per_second,
                pass_rate=item.pass_rate_percent,
            )
        )
    return "\n".join(lines)


def _parse_run_argument(raw_value: str) -> tuple[str | None, Path]:
    """Parse ``label=path`` or plain ``path`` for ``--run`` values."""

    if "=" in raw_value:
        label, raw_path = raw_value.split("=", 1)
        if label.strip():
            return label.strip(), Path(raw_path).expanduser()
        return None, Path(raw_path).expanduser()
    return None, Path(raw_value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""

    parser = argparse.ArgumentParser(description="Compare evaluation JSONL runs and print a markdown table.")
    parser.add_argument("--run-a", required=True, help="Path to run A JSONL file.")
    parser.add_argument("--run-b", required=True, help="Path to run B JSONL file.")
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        help="Optional additional run as 'path' or 'label=path'. Can be repeated.",
    )
    parser.add_argument(
        "--label-a",
        default="run-a",
        help="Display label for --run-a in output table (default: run-a).",
    )
    parser.add_argument(
        "--label-b",
        default="run-b",
        help="Display label for --run-b in output table (default: run-b).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    run_specs: list[tuple[str | None, Path]] = [
        (args.label_a, Path(args.run_a).expanduser()),
        (args.label_b, Path(args.run_b).expanduser()),
    ]

    for raw in args.run:
        run_specs.append(_parse_run_argument(raw))

    metrics: list[RunMetrics] = []
    for label, path in run_specs:
        metrics.append(load_run_metrics(path, run_label=label))

    print(render_markdown_table(metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
