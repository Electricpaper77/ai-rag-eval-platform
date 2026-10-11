from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import container_runtime_smoke


def test_container_runtime_smoke_matches_request_ids_and_redacts_secret(tmp_path: Path, monkeypatch) -> None:
    artifact_dir = tmp_path / "artifacts"
    eval_log = artifact_dir / "eval_runs" / "eval_runs.jsonl"
    inference_log = artifact_dir / "inference_runs.jsonl"
    eval_log.parent.mkdir(parents=True)
    inference_log.parent.mkdir(parents=True, exist_ok=True)

    def fake_request(method: str, url: str, payload=None):
        if url.endswith("/health"):
            return 200, {"status": "ok"}
        if url.endswith("/metrics"):
            return 200, "# HELP eval_requests_total\n"
        if url.endswith("/openapi.json"):
            return 200, {"info": {"title": "AI RAG Eval Platform"}}
        if url.endswith("/evaluate"):
            eval_log.write_text(
                json.dumps({"run_id": "eval-ci", "trace_id": "trace-abc", "metadata": payload["metadata"]}) + "\n",
                encoding="utf-8",
            )
            return 200, {"pass": True, "score": 1.0, "failure_reasons": [], "metrics": {}, "run_id": "eval-ci"}
        if url.endswith("/v1/chat/completions") and payload == {"model": "gpt-4o-mini"}:
            return 400, {"detail": "messages field required"}
        if url.endswith("/v1/chat/completions"):
            inference_log.write_text(json.dumps({"request_id": "chatcmpl-ci", "success": True}) + "\n", encoding="utf-8")
            return 200, {
                "request_id": "chatcmpl-ci",
                "routing": {"selected_runtime": "mock", "gpu_availability": False},
            }
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setattr(container_runtime_smoke, "_request", fake_request)

    report = container_runtime_smoke.run_smoke("http://127.0.0.1:8080", artifact_dir)

    assert report["valid_evaluation"]["run_id"] == "eval-ci"
    assert report["invalid_request"]["status_code"] == 400
    assert report["mock_fallback_when_gpu_unavailable"]["selected_runtime"] == "mock"
    assert report["request_id_tracing"]["eval_trace_id"] == "trace-abc"
    assert report["request_id_tracing"]["chat_request_id_logged"] == "chatcmpl-ci"
    assert (artifact_dir / "container_runtime_smoke_report.json").exists()


def test_secret_canary_detection_fails_closed() -> None:
    with pytest.raises(AssertionError, match="secret canary leaked"):
        container_runtime_smoke._assert_no_secret_leak({"value": container_runtime_smoke.SECRET_CANARY})
