from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

ARTIFACTS_ROOT = Path("artifacts")
EVALS_DIR = ARTIFACTS_ROOT / "evals"
ROUTING_DIR = ARTIFACTS_ROOT / "routing"
BENCHMARKS_DIR = ARTIFACTS_ROOT / "benchmarks"
RUN_METADATA_PATH = ARTIFACTS_ROOT / "run_metadata.json"


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
    for folder in (EVALS_DIR, ROUTING_DIR, BENCHMARKS_DIR):
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


def _compute_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {
            "eval_pass_rate": 0.0,
            "hallucination_rate": 0.0,
            "citation_precision": 0.0,
            "refusal_accuracy": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "tokens_per_second": 0.0,
            "cost_per_request": 0.0,
        }

    pass_values: list[float] = []
    hallucination_values: list[float] = []
    citation_precision_values: list[float] = []
    refusal_accuracy_values: list[float] = []
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

        refusal_accuracy = _as_float(row.get("refusal_accuracy"))
        if refusal_accuracy is None:
            refusal_correct = _as_bool(row.get("refusal_correct"))
            if refusal_correct is not None:
                refusal_accuracy = 1.0 if refusal_correct else 0.0
        if refusal_accuracy is not None:
            refusal_accuracy_values.append(refusal_accuracy)

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
        "refusal_accuracy": float(mean(refusal_accuracy_values)) if refusal_accuracy_values else 0.0,
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "tokens_per_second": float(mean(tps_values)) if tps_values else 0.0,
        "cost_per_request": float(mean(costs)) if costs else 0.0,
    }


def _group_runs(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        run_id = str(row.get("run_id") or Path(row.get("_source_file", "unknown.jsonl")).stem)
        grouped.setdefault(run_id, []).append(row)
    return grouped


@router.get("/dashboard/summary")
def dashboard_summary() -> dict[str, float]:
    rows = _iter_jsonl_rows()
    metrics = _compute_metrics(rows)
    return {
        "eval_pass_rate": metrics["eval_pass_rate"],
        "hallucination_rate": metrics["hallucination_rate"],
        "citation_precision": metrics["citation_precision"],
        "p95_latency_ms": metrics["p95_latency_ms"],
        "cost_per_request": metrics["cost_per_request"],
    }


@router.get("/dashboard/runs")
def dashboard_runs() -> list[dict[str, Any]]:
    rows = _iter_jsonl_rows()
    grouped = _group_runs(rows)
    metadata = _load_metadata()

    runs: list[dict[str, Any]] = []
    for run_id, run_rows in sorted(grouped.items()):
        run_metrics = _compute_metrics(run_rows)
        meta = metadata.get(run_id, {})
        runs.append(
            {
                "run_id": run_id,
                "model_version": meta.get("model_version") or run_rows[0].get("model_version") or "unknown",
                "prompt_version": meta.get("prompt_version") or run_rows[0].get("prompt_version") or "unknown",
                "dataset_version": meta.get("dataset_version") or run_rows[0].get("dataset_version") or "unknown",
                "timestamp": meta.get("timestamp") or run_rows[0].get("timestamp") or "unknown",
                "metrics": run_metrics,
            }
        )
    return runs


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page() -> str:
    runs = dashboard_runs()
    table_rows = "\n".join(
        (
            "<tr>"
            f"<td>{run['run_id']}</td>"
            f"<td>{run['model_version']}</td>"
            f"<td>{run['metrics']['eval_pass_rate']:.3f}</td>"
            f"<td>{run['metrics']['hallucination_rate']:.3f}</td>"
            f"<td>{run['metrics']['p95_latency_ms']:.2f}</td>"
            f"<td>{run['metrics']['cost_per_request']:.4f}</td>"
            "</tr>"
        )
        for run in runs
    )

    return f"""
    <html>
      <head>
        <title>Evaluation Dashboard</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 24px; }}
          table {{ border-collapse: collapse; width: 100%; }}
          th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
          th {{ background-color: #f4f4f4; }}
        </style>
      </head>
      <body>
        <h1>Evaluation Dashboard</h1>
        <table>
          <thead>
            <tr>
              <th>run_id</th>
              <th>model</th>
              <th>eval_pass_rate</th>
              <th>hallucination_rate</th>
              <th>p95_latency</th>
              <th>cost_per_request</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
      </body>
    </html>
    """
