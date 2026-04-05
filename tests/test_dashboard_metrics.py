from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.routes import dashboard as dashboard_routes


client = TestClient(app)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_dashboard_summary_and_runs(tmp_path: Path, monkeypatch) -> None:
    artifacts_root = tmp_path / "artifacts"
    evals_dir = artifacts_root / "evals"
    routing_dir = artifacts_root / "routing"
    benchmarks_dir = artifacts_root / "benchmarks"
    metadata_path = artifacts_root / "run_metadata.json"

    _write_jsonl(
        evals_dir / "eval1.jsonl",
        [
            {
                "run_id": "run-a",
                "passed": True,
                "hallucination": False,
                "citation_precision": 0.9,
                "refusal_accuracy": 1.0,
                "latency_ms": 100,
                "tokens_per_second": 50,
                "cost_per_request": 0.01,
            },
            {
                "run_id": "run-a",
                "passed": False,
                "hallucination": True,
                "citation_precision": 0.7,
                "refusal_accuracy": 0.0,
                "latency_ms": 200,
                "tokens_per_second": 40,
                "cost_per_request": 0.02,
            },
        ],
    )
    _write_jsonl(
        routing_dir / "route1.jsonl",
        [
            {
                "run_id": "run-b",
                "eval_pass": True,
                "is_hallucination": False,
                "citation_precision": 0.8,
                "refusal_correct": True,
                "response_latency_ms": 300,
                "tokens_per_sec": 30,
                "cost_usd": 0.03,
            }
        ],
    )
    _write_jsonl(
        benchmarks_dir / "bench1.jsonl",
        [
            {
                "run_id": "run-c",
                "pass": True,
                "hallucination": False,
                "citation_precision": 1.0,
                "latency_ms": 50,
                "output_tokens": 100,
                "cost": 0.005,
            }
        ],
    )

    metadata_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "run-a",
                        "model_version": "model-a",
                        "prompt_version": "prompt-a",
                        "dataset_version": "dataset-a",
                        "timestamp": "2026-04-05T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(dashboard_routes, "ARTIFACTS_ROOT", artifacts_root)
    monkeypatch.setattr(dashboard_routes, "EVALS_DIR", evals_dir)
    monkeypatch.setattr(dashboard_routes, "ROUTING_DIR", routing_dir)
    monkeypatch.setattr(dashboard_routes, "BENCHMARKS_DIR", benchmarks_dir)
    monkeypatch.setattr(dashboard_routes, "RUN_METADATA_PATH", metadata_path)

    summary_resp = client.get("/dashboard/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()

    assert summary["eval_pass_rate"] == 0.75
    assert summary["hallucination_rate"] == 0.25
    assert summary["citation_precision"] == 0.85
    assert summary["p95_latency_ms"] == 300.0
    assert summary["cost_per_request"] == 0.01625

    runs_resp = client.get("/dashboard/runs")
    assert runs_resp.status_code == 200
    runs = runs_resp.json()
    assert len(runs) == 3

    run_a = next(run for run in runs if run["run_id"] == "run-a")
    assert run_a["model_version"] == "model-a"
    assert run_a["metrics"]["eval_pass_rate"] == 0.5

    html_resp = client.get("/dashboard")
    assert html_resp.status_code == 200
    assert "Evaluation Dashboard" in html_resp.text
    assert "run-a" in html_resp.text
