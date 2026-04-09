from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.observability.artifact_store import InferenceArtifactStore
from backend.app.observability.performance import compute_performance_metrics
from backend.app.observability.service import INFERENCE_OBSERVABILITY

client = TestClient(app)


def test_compute_performance_metrics_returns_realistic_phase_breakdown() -> None:
    metrics = compute_performance_metrics(latency_ms=240.0, tokens_out=120)

    assert metrics.queue_time_ms > 0
    assert metrics.ttft_ms > 0
    assert metrics.decode_time_ms > 0
    assert metrics.tokens_per_second > 0
    assert round(metrics.queue_time_ms + metrics.ttft_ms + metrics.decode_time_ms, 1) == 240.0


def test_chat_completions_persists_structured_observability_artifact(tmp_path: Path, monkeypatch) -> None:
    store = InferenceArtifactStore(root_dir=tmp_path / "artifacts" / "inference_events")
    monkeypatch.setattr(INFERENCE_OBSERVABILITY, "_artifact_store", store)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Summarize GPU utilization for 8xH100 clusters."},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["request_id"]
    assert payload["performance"]["ttft_ms"] > 0
    assert payload["performance"]["tokens_per_second"] > 0

    now = datetime.now(timezone.utc)
    partition = store.root_dir / f"year={now.year}" / f"month={now.month:02d}" / f"day={now.day:02d}" / "inference_events.jsonl"
    assert partition.exists()

    last_event = json.loads(partition.read_text(encoding="utf-8").splitlines()[-1])
    assert last_event["request_id"] == payload["request_id"]
    assert last_event["status"] == "ok"
    assert last_event["performance"]["ttft_ms"] == payload["performance"]["ttft_ms"]
    assert last_event["performance"]["tokens_out"] == payload["tokens_out"]

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    assert "inference_pipeline_events_total" in metrics_resp.text
    assert "inference_ttft_ms" in metrics_resp.text
