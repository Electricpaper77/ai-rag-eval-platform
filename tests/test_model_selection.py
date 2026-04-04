from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.model_selector as model_selector


client = TestClient(app)


def test_select_best_model_and_output_created(tmp_path: Path, monkeypatch) -> None:
    eval_summary_path = tmp_path / "eval_dashboard_summary.json"
    best_model_path = tmp_path / "best_model.json"

    payload = {
        "runs": [
            {
                "run_id": "mistral_eval",
                "p95_latency_ms": 900,
                "pass_rate": 0.86,
                "hallucination_rate": 0.08,
                "tokens_per_sec_avg": 42,
            },
            {
                "run_id": "llama_eval",
                "p95_latency_ms": 700,
                "pass_rate": 0.91,
                "hallucination_rate": 0.05,
                "tokens_per_sec_avg": 35,
            },
        ]
    }
    eval_summary_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(model_selector, "EVAL_SUMMARY_PATH", eval_summary_path)
    monkeypatch.setattr(model_selector, "BEST_MODEL_PATH", best_model_path)

    result = model_selector.select_best_model()

    assert result["selected_model"] == "llama_eval"
    assert result["score"] == 0.2844
    assert best_model_path.exists()

    persisted = json.loads(best_model_path.read_text(encoding="utf-8"))
    assert persisted["selected_model"] == "llama_eval"
    assert persisted["score"] == 0.2844


def test_best_model_endpoint_returns_selection(tmp_path: Path, monkeypatch) -> None:
    eval_summary_path = tmp_path / "eval_dashboard_summary.json"
    best_model_path = tmp_path / "best_model.json"

    payload = {
        "runs": [
            {
                "run_id": "model_a",
                "p95_latency_ms": 500,
                "pass_rate": 0.8,
                "hallucination_rate": 0.03,
                "tokens_per_sec_avg": 60,
            },
            {
                "run_id": "model_b",
                "p95_latency_ms": 700,
                "pass_rate": 0.75,
                "hallucination_rate": 0.04,
                "tokens_per_sec_avg": 65,
            },
        ]
    }
    eval_summary_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(model_selector, "EVAL_SUMMARY_PATH", eval_summary_path)
    monkeypatch.setattr(model_selector, "BEST_MODEL_PATH", best_model_path)

    response = client.get("/platform/best-model")
    assert response.status_code == 200

    body = response.json()
    assert body["selected_model"] == "model_a"
    assert "score" in body
    assert best_model_path.exists()
