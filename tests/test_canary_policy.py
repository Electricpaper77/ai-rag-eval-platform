from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.canary_controller as canary_controller
import gpu_platform.request_router as request_router
import gpu_platform.router_policies as router_policies


client = TestClient(app)


def _configure(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    jobs_dir = tmp_path / "artifacts" / "platform_jobs"
    proof_dir = tmp_path / "artifacts" / "proof"
    canary_decisions = jobs_dir / "canary_decisions.jsonl"
    canary_summary = proof_dir / "canary_summary.json"

    monkeypatch.setattr(canary_controller, "CANARY_DECISIONS_PATH", canary_decisions)
    monkeypatch.setattr(canary_controller, "CANARY_SUMMARY_PATH", canary_summary)

    eval_summary_path = proof_dir / "eval_dashboard_summary.json"
    eval_summary_path.parent.mkdir(parents=True, exist_ok=True)
    eval_summary_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "vllm_primary",
                        "pass_rate": 0.92,
                        "hallucination_rate": 0.03,
                        "p95_latency_ms": 700,
                        "tokens_per_sec_avg": 80,
                    },
                    {
                        "run_id": "openai_primary",
                        "pass_rate": 0.91,
                        "hallucination_rate": 0.04,
                        "p95_latency_ms": 2000,
                        "tokens_per_sec_avg": 60,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(router_policies, "EVAL_SUMMARY_PATH", eval_summary_path)

    request_router.PREFIX_CACHE.clear()
    canary_controller.CANARY_CONTROLLER.stop()
    return canary_decisions, canary_summary


def _chat_payload() -> dict:
    return {
        "messages": [{"role": "system", "content": "canary"}, {"role": "user", "content": "hello"}],
        "latency_budget_ms": 2500,
        "quality_tier": "balanced",
    }


def test_canary_split_and_status_endpoint(tmp_path: Path, monkeypatch) -> None:
    canary_decisions, _ = _configure(tmp_path, monkeypatch)

    started = client.post(
        "/platform/canary/start",
        json={
            "baseline_backend": "vllm",
            "candidate_backend": "openai",
            "canary_percent": 10,
            "max_p95_latency_ms": 10000,
            "min_pass_rate": 0.0,
            "max_hallucination_rate": 1.0,
        },
    )
    assert started.status_code == 200

    routed = [
        client.post("/platform/chat", json=_chat_payload()).json()["active_backend"]
        for _ in range(100)
    ]
    candidate_count = sum(1 for backend in routed if backend == "openai")
    assert 5 <= candidate_count <= 15

    status = client.get("/platform/canary/status")
    assert status.status_code == 200
    body = status.json()
    assert body["active"] is True
    assert body["policy"]["candidate_backend"] == "openai"

    assert canary_decisions.exists()


def test_rollback_triggers_and_summary_created(tmp_path: Path, monkeypatch) -> None:
    _, canary_summary = _configure(tmp_path, monkeypatch)

    client.post(
        "/platform/canary/start",
        json={
            "baseline_backend": "vllm",
            "candidate_backend": "openai",
            "canary_percent": 100,
            "max_p95_latency_ms": 1000,
            "min_pass_rate": 0.0,
            "max_hallucination_rate": 1.0,
        },
    )

    response = client.post("/platform/chat", json=_chat_payload())
    assert response.status_code == 200

    status = client.get("/platform/canary/status").json()
    assert status["rollback_triggered"] is True
    assert status["rollback_reason"] == "p95 latency exceeded threshold"

    assert canary_summary.exists()
    summary = json.loads(canary_summary.read_text(encoding="utf-8"))
    assert summary["rollback_triggered"] is True
    assert summary["candidate_backend"] == "openai"


def test_canary_stop_endpoint(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)

    client.post(
        "/platform/canary/start",
        json={
            "baseline_backend": "vllm",
            "candidate_backend": "openai",
            "canary_percent": 20,
            "max_p95_latency_ms": 5000,
            "min_pass_rate": 0.5,
            "max_hallucination_rate": 0.5,
        },
    )

    stopped = client.post("/platform/canary/stop")
    assert stopped.status_code == 200
    assert stopped.json()["stopped"] is True

    status = client.get("/platform/canary/status").json()
    assert status["active"] is False
