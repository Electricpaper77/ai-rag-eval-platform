from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

ARTIFACTS_ROOT = Path("artifacts")
EVALS_DIR = ARTIFACTS_ROOT / "evals"
BENCHMARKS_DIR = ARTIFACTS_ROOT / "benchmarks"
RUN_METADATA_PATH = ARTIFACTS_ROOT / "run_metadata.json"
BEST_MODEL_PATH = Path("artifacts/platform_jobs/best_model.json")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return float(ordered[idx])


def _iter_jsonl_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for folder in (EVALS_DIR, BENCHMARKS_DIR):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.jsonl")):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    record["_source_file"] = path.name
                    rows.append(record)
    return rows


def _load_metadata() -> dict[str, dict[str, Any]]:
    if not RUN_METADATA_PATH.exists():
        return {}
    with RUN_METADATA_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    runs = payload.get("runs", payload)
    if isinstance(runs, list):
        return {str(item.get("run_id")): item for item in runs if item.get("run_id")}
    if isinstance(runs, dict):
        return {str(k): v for k, v in runs.items()}
    return {}


def _group_runs(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        run_id = str(row.get("run_id") or Path(row.get("_source_file", "unknown.jsonl")).stem)
        grouped.setdefault(run_id, []).append(row)
    return grouped


def _compute_run_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    pass_values: list[float] = []
    hallucination_values: list[float] = []
    citation_precision_values: list[float] = []
    latencies: list[float] = []
    tps_values: list[float] = []
    costs: list[float] = []

    for row in rows:
        passed = _as_bool(row.get("passed"))
        if passed is None:
            passed = _as_bool(row.get("eval_pass"))
        if passed is None:
            passed = _as_bool(row.get("pass"))
        if passed is not None:
            pass_values.append(1.0 if passed else 0.0)

        hallucination = _as_bool(row.get("hallucination"))
        if hallucination is None:
            hallucination = _as_bool(row.get("is_hallucination"))
        if hallucination is not None:
            hallucination_values.append(1.0 if hallucination else 0.0)

        citation_precision = _as_float(row.get("citation_precision"))
        if citation_precision is not None:
            citation_precision_values.append(citation_precision)

        latency = _as_float(row.get("latency_ms"))
        if latency is None:
            latency = _as_float(row.get("response_latency_ms"))
        if latency is not None:
            latencies.append(latency)

        tps = _as_float(row.get("tokens_per_second"))
        if tps is None:
            tps = _as_float(row.get("tokens_per_sec"))
        if tps is None:
            output_tokens = _as_float(row.get("output_tokens"))
            if output_tokens is None:
                output_tokens = _as_float(row.get("completion_tokens"))
            if output_tokens is not None and latency and latency > 0:
                tps = output_tokens / (latency / 1000.0)
        if tps is not None:
            tps_values.append(tps)

        cost = _as_float(row.get("cost_per_request"))
        if cost is None:
            cost = _as_float(row.get("cost_usd"))
        if cost is None:
            cost = _as_float(row.get("cost"))
        if cost is not None:
            costs.append(cost)

    return {
        "eval_pass_rate": float(mean(pass_values)) if pass_values else 0.0,
        "hallucination_rate": float(mean(hallucination_values)) if hallucination_values else 0.0,
        "citation_precision": float(mean(citation_precision_values)) if citation_precision_values else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "tokens_per_second": float(mean(tps_values)) if tps_values else 0.0,
        "cost_per_request": float(mean(costs)) if costs else 0.0,
    }


def _inverse_safe(value: float) -> float:
    if value <= 0:
        return 0.0
    return 1.0 / value


def select_best_model(
    quality_weight: float = 0.5,
    latency_weight: float = 0.3,
    cost_weight: float = 0.2,
) -> dict[str, Any]:
    rows = _iter_jsonl_rows()
    grouped = _group_runs(rows)
    if not grouped:
        raise ValueError("No runs found in artifacts/evals or artifacts/benchmarks")

    metadata = _load_metadata()
    scored_runs: list[dict[str, Any]] = []

    for run_id, run_rows in sorted(grouped.items()):
        run_metrics = _compute_run_metrics(run_rows)
        model_name = str(
            metadata.get(run_id, {}).get("model_version")
            or run_rows[0].get("model_version")
            or run_id
        )
        quality_score = (
            run_metrics["eval_pass_rate"]
            - run_metrics["hallucination_rate"]
            + run_metrics["citation_precision"]
        )
        latency_score = _inverse_safe(run_metrics["p95_latency_ms"])
        cost_score = _inverse_safe(run_metrics["cost_per_request"])
        final_score = (
            quality_weight * quality_score
            + latency_weight * latency_score
            + cost_weight * cost_score
        )

        scored_runs.append(
            {
                "run_id": run_id,
                "model": model_name,
                "final_score": float(round(final_score, 6)),
                "quality_score": float(round(quality_score, 6)),
                "latency_score": float(round(latency_score, 6)),
                "cost_score": float(round(cost_score, 6)),
                "metrics": run_metrics,
            }
        )

    best = max(scored_runs, key=lambda x: x["final_score"])
    result = {
        "selected_model": best["model"],
        "run_id": best["run_id"],
        "score": best["final_score"],
        "weights": {
            "quality_weight": quality_weight,
            "latency_weight": latency_weight,
            "cost_weight": cost_weight,
        },
        "metrics": {
            "eval_pass_rate": best["metrics"]["eval_pass_rate"],
            "hallucination_rate": best["metrics"]["hallucination_rate"],
            "citation_precision": best["metrics"]["citation_precision"],
            "p95_latency_ms": best["metrics"]["p95_latency_ms"],
            "tokens_per_second": best["metrics"]["tokens_per_second"],
            "cost_per_request": best["metrics"]["cost_per_request"],
        },
    }

    BEST_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    BEST_MODEL_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result
