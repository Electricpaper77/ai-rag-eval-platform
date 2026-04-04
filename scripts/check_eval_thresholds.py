#!/usr/bin/env python3
"""Regression gate for evaluation run artifacts.

Reads threshold values from ``eval_thresholds.yaml``, finds the latest JSONL
artifact, computes aggregate metrics, and exits non-zero when thresholds are
violated.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

PASS_KEYS: tuple[str, ...] = ("eval_pass", "pass", "passed")


@dataclass(frozen=True)
class Thresholds:
    min_pass_rate: float
    max_p95_latency_ms: float
    min_tokens_per_sec: float


@dataclass(frozen=True)
class Metrics:
    pass_rate: float
    p95_latency_ms: float
    tokens_per_sec: float
    total_rows: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail CI when latest eval JSONL metrics violate configured thresholds."
    )
    parser.add_argument(
        "--config",
        default="eval_thresholds.yaml",
        help="Path to threshold config file (default: eval_thresholds.yaml).",
    )
    parser.add_argument(
        "--artifact",
        default=None,
        help="Optional explicit JSONL artifact path. If omitted, latest run artifact is used.",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="runs",
        help="Directory to search for latest *.jsonl artifact (default: runs).",
    )
    return parser.parse_args()


def _parse_simple_yaml(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if ":" not in stripped:
                raise ValueError(f"Invalid line {line_number} in {path}: expected key: value")

            key, raw_value = stripped.split(":", 1)
            key = key.strip()
            value_text = raw_value.strip()
            if not key:
                raise ValueError(f"Invalid line {line_number} in {path}: missing key")
            if not value_text:
                raise ValueError(f"Invalid line {line_number} in {path}: missing value")

            try:
                values[key] = float(value_text)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid numeric value for '{key}' on line {line_number} in {path}: {value_text}"
                ) from exc

    return values


def load_thresholds(path: Path) -> Thresholds:
    if not path.exists():
        raise FileNotFoundError(f"Threshold config not found: {path}")

    raw = _parse_simple_yaml(path)
    required = ("min_pass_rate", "max_p95_latency_ms", "min_tokens_per_sec")
    missing = [name for name in required if name not in raw]
    if missing:
        raise ValueError(f"Missing threshold keys in {path}: {', '.join(missing)}")

    return Thresholds(
        min_pass_rate=raw["min_pass_rate"],
        max_p95_latency_ms=raw["max_p95_latency_ms"],
        min_tokens_per_sec=raw["min_tokens_per_sec"],
    )


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


def _extract_latency_ms(row: dict[str, object]) -> float | None:
    latency = row.get("latency_ms")
    try:
        value = float(latency)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


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


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * (percentile / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def load_metrics(jsonl_path: Path) -> Metrics:
    pass_count = 0
    total = 0
    latencies_ms: list[float] = []
    tokens_per_second: list[float] = []

    with jsonl_path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {jsonl_path}:{line_number}: {exc}") from exc

            if not isinstance(row, dict):
                raise ValueError(
                    f"Expected object JSON at {jsonl_path}:{line_number}, got {type(row).__name__}"
                )

            total += 1

            if _extract_pass_value(row):
                pass_count += 1

            latency = _extract_latency_ms(row)
            if latency is not None:
                latencies_ms.append(latency)

            tps = _extract_tokens_per_second(row)
            if tps is not None:
                tokens_per_second.append(tps)

    if total == 0:
        raise ValueError(f"No evaluation rows found in {jsonl_path}")

    pass_rate = pass_count / total
    p95_latency_ms = _percentile(latencies_ms, 95)
    avg_tps = sum(tokens_per_second) / len(tokens_per_second) if tokens_per_second else 0.0

    return Metrics(
        pass_rate=pass_rate,
        p95_latency_ms=p95_latency_ms,
        tokens_per_sec=avg_tps,
        total_rows=total,
    )


def find_latest_artifact(artifacts_dir: Path) -> Path:
    if not artifacts_dir.exists():
        raise FileNotFoundError(f"Artifact directory not found: {artifacts_dir}")

    candidates = [path for path in artifacts_dir.glob("*.jsonl") if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No JSONL artifacts found in {artifacts_dir}")

    return max(candidates, key=lambda path: path.stat().st_mtime)


def evaluate(metrics: Metrics, thresholds: Thresholds) -> list[str]:
    failures: list[str] = []

    if metrics.pass_rate < thresholds.min_pass_rate:
        failures.append(
            "pass rate {:.2%} below threshold {:.2%}".format(
                metrics.pass_rate,
                thresholds.min_pass_rate,
            )
        )

    if metrics.p95_latency_ms > thresholds.max_p95_latency_ms:
        failures.append(
            "p95 latency {:.0f}ms exceeds threshold {:.0f}ms".format(
                metrics.p95_latency_ms,
                thresholds.max_p95_latency_ms,
            )
        )

    if metrics.tokens_per_sec < thresholds.min_tokens_per_sec:
        failures.append(
            "tokens/sec {:.2f} below threshold {:.2f}".format(
                metrics.tokens_per_sec,
                thresholds.min_tokens_per_sec,
            )
        )

    return failures


def main() -> int:
    args = parse_args()
    thresholds = load_thresholds(Path(args.config))

    artifact_path = Path(args.artifact) if args.artifact else find_latest_artifact(Path(args.artifacts_dir))
    metrics = load_metrics(artifact_path)

    failures = evaluate(metrics, thresholds)
    if failures:
        print(f"FAIL: {failures[0]}")
        if len(failures) > 1:
            for reason in failures[1:]:
                print(f"FAIL: {reason}")
        return 1

    print(
        "PASS: pass rate {:.2%}, p95 latency {:.0f}ms, tokens/sec {:.2f} ({})".format(
            metrics.pass_rate,
            metrics.p95_latency_ms,
            metrics.tokens_per_sec,
            artifact_path,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
