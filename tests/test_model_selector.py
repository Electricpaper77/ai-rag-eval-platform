from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.routes import dashboard as dashboard_routes
import gpu_platform.model_selector as model_selector


client = TestClient(app)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_select_best_model_persists_metadata(tmp_path: Path, monkeypatch) -> None:
    artifacts_root = tmp_path / "artifacts"
    evals_dir = artifacts_root / "evals"
    routing_dir = artifacts_root / "routing"
    benchmarks_dir = artifacts_root / "benchmarks"
    metadata_path = artifacts_root / "run_metadata.json"
    best_model_path = artifacts_root / "platform_jobs" / "best_model.json"

    _write_jsonl(
        evals_dir / "eval_a.jsonl",
        [
            {
                "run_id": "run-a",
                "model_version": "mistral-7b-instruct",
                "passed": True,
                "hallucination": False,
                "citation_precision": 0.9,
                "latency_ms": 1180,
                "tokens_per_second": 70,
                "cost_per_request": 0.006,
            },
            {
                "run_id": "run-a",
                "model_version": "mistral-7b-instruct",
                "passed": True,
                "hallucination": False,
                "citation_precision": 0.84,
                "latency_ms": 1100,
                "tokens_per_second": 74,
                "cost_per_request": 0.006,
            },
        ],
    )
    _write_jsonl(
        benchmarks_dir / "bench_b.jsonl",
        [
            {
                "run_id": "run-b",
                "model_version": "llama-3.1-8b",
                "eval_pass": True,
                "is_hallucination": False,
                "citation_precision": 0.72,
                "response_latency_ms": 950,
                "output_tokens": 160,
                "cost": 0.01,
            },
            {
                "run_id": "run-b",
                "model_version": "llama-3.1-8b",
                "eval_pass": False,
                "is_hallucination": True,
                "citation_precision": 0.68,
                "response_latency_ms": 990,
                "output_tokens": 120,
                "cost": 0.01,
            },
        ],
    )
    metadata_path.write_text(
        json.dumps(
            {
                "runs": [
                    {"run_id": "run-a", "model_version": "mistral-7b-instruct"},
                    {"run_id": "run-b", "model_version": "llama-3.1-8b"},
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(model_selector, "ARTIFACTS_ROOT", artifacts_root)
    monkeypatch.setattr(model_selector, "EVALS_DIR", evals_dir)
    monkeypatch.setattr(model_selector, "BENCHMARKS_DIR", benchmarks_dir)
    monkeypatch.setattr(model_selector, "RUN_METADATA_PATH", metadata_path)
    monkeypatch.setattr(model_selector, "BEST_MODEL_PATH", best_model_path)
    monkeypatch.setattr(dashboard_routes, "ARTIFACTS_ROOT", artifacts_root)
    monkeypatch.setattr(dashboard_routes, "EVALS_DIR", evals_dir)
    monkeypatch.setattr(dashboard_routes, "ROUTING_DIR", routing_dir)
    monkeypatch.setattr(dashboard_routes, "BENCHMARKS_DIR", benchmarks_dir)
    monkeypatch.setattr(dashboard_routes, "RUN_METADATA_PATH", metadata_path)

    result = model_selector.select_best_model()

    assert result["selected_model"] == "mistral-7b-instruct"
    assert "score" in result
    assert result["metrics"]["eval_pass_rate"] == 1.0
    assert result["metrics"]["p95_latency_ms"] == 1180.0
    assert result["metrics"]["cost_per_request"] == 0.006
    assert best_model_path.exists()

    persisted = json.loads(best_model_path.read_text(encoding="utf-8"))
    assert persisted["selected_model"] == "mistral-7b-instruct"
    assert persisted["metrics"]["citation_precision"] == 0.87


def test_best_model_and_leaderboard_endpoints(tmp_path: Path, monkeypatch) -> None:
    artifacts_root = tmp_path / "artifacts"
    evals_dir = artifacts_root / "evals"
    routing_dir = artifacts_root / "routing"
    benchmarks_dir = artifacts_root / "benchmarks"
    metadata_path = artifacts_root / "run_metadata.json"
    best_model_path = artifacts_root / "platform_jobs" / "best_model.json"

    _write_jsonl(
        evals_dir / "eval.jsonl",
        [
            {
                "run_id": "model-x-run",
                "model_version": "model-x",
                "passed": True,
                "hallucination": False,
                "citation_precision": 0.95,
                "latency_ms": 1200,
                "cost_per_request": 0.005,
            },
            {
                "run_id": "model-y-run",
                "model_version": "model-y",
                "passed": True,
                "hallucination": False,
                "citation_precision": 0.5,
                "latency_ms": 300,
                "cost_per_request": 0.015,
            },
        ],
    )
    _write_jsonl(benchmarks_dir / "bench.jsonl", [])
    metadata_path.write_text(
        json.dumps(
            {
                "runs": [
                    {"run_id": "model-x-run", "model_version": "model-x"},
                    {"run_id": "model-y-run", "model_version": "model-y"},
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(model_selector, "ARTIFACTS_ROOT", artifacts_root)
    monkeypatch.setattr(model_selector, "EVALS_DIR", evals_dir)
    monkeypatch.setattr(model_selector, "BENCHMARKS_DIR", benchmarks_dir)
    monkeypatch.setattr(model_selector, "RUN_METADATA_PATH", metadata_path)
    monkeypatch.setattr(model_selector, "BEST_MODEL_PATH", best_model_path)
    monkeypatch.setattr(dashboard_routes, "ARTIFACTS_ROOT", artifacts_root)
    monkeypatch.setattr(dashboard_routes, "EVALS_DIR", evals_dir)
    monkeypatch.setattr(dashboard_routes, "ROUTING_DIR", routing_dir)
    monkeypatch.setattr(dashboard_routes, "BENCHMARKS_DIR", benchmarks_dir)
    monkeypatch.setattr(dashboard_routes, "RUN_METADATA_PATH", metadata_path)

    best_resp = client.get("/platform/best-model")
    assert best_resp.status_code == 200
    best_payload = best_resp.json()
    assert best_payload["selected_model"] == "model-x"
    assert "weights" in best_payload

    leaderboard_resp = client.get("/dashboard/leaderboard")
    assert leaderboard_resp.status_code == 200
    assert "Multi-Model Leaderboard" in leaderboard_resp.text
    assert "final_score" in leaderboard_resp.text
    assert "model-x" in leaderboard_resp.text
