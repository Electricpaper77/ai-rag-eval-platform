from __future__ import annotations

import json
from pathlib import Path
import sys
import time

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.request_router as request_router
import gpu_platform.router_policies as router_policies
import gpu_platform.shadow_eval as shadow_eval


client = TestClient(app)


def _configure_paths(tmp_path: Path, monkeypatch) -> Path:
    log_path = tmp_path / "artifacts" / "shadow_runs" / "shadow_eval.jsonl"
    summary_path = tmp_path / "artifacts" / "proof" / "shadow_eval_summary.json"

    monkeypatch.setattr(shadow_eval, "SHADOW_LOG_PATH", log_path)
    monkeypatch.setattr(shadow_eval, "SHADOW_SUMMARY_PATH", summary_path)

    eval_summary_path = tmp_path / "artifacts" / "proof" / "eval_dashboard_summary.json"
    eval_summary_path.parent.mkdir(parents=True, exist_ok=True)
    eval_summary_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "run_id": "vllm_primary",
                        "pass_rate": 0.9,
                        "hallucination_rate": 0.05,
                        "p95_latency_ms": 700,
                        "tokens_per_sec_avg": 85,
                    },
                    {
                        "run_id": "openai_primary",
                        "pass_rate": 0.93,
                        "hallucination_rate": 0.03,
                        "p95_latency_ms": 1050,
                        "tokens_per_sec_avg": 65,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(router_policies, "EVAL_SUMMARY_PATH", eval_summary_path)
    request_router.PREFIX_CACHE.clear()
    return log_path


def _wait_for_lines(path: Path, min_lines: int, timeout_s: float = 2.0) -> list[str]:
    started = time.time()
    while time.time() - started <= timeout_s:
        if path.exists():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if len(lines) >= min_lines:
                return lines
        time.sleep(0.05)
    return []


def test_shadow_logging_on_force_shadow(tmp_path: Path, monkeypatch) -> None:
    log_path = _configure_paths(tmp_path, monkeypatch)

    body = request_router.route_request(
        messages=[{"role": "user", "content": "What is shadow eval?"}],
        latency_budget_ms=1500,
        quality_tier="speed",
        request_id="shadow-force-001",
        force_shadow=True,
    )

    assert body["response"].startswith("[")
    lines = _wait_for_lines(log_path, min_lines=1)
    assert len(lines) == 1

    row = json.loads(lines[0])
    assert row["request_id"] == "shadow-force-001"
    assert row["primary_model"]
    assert row["shadow_model"]
    assert isinstance(row["primary_latency_ms"], float)
    assert isinstance(row["shadow_latency_ms"], float)


def test_balanced_quality_tier_always_runs_shadow(tmp_path: Path, monkeypatch) -> None:
    log_path = _configure_paths(tmp_path, monkeypatch)

    request_router.route_request(
        messages=[{"role": "user", "content": "hello"}],
        latency_budget_ms=1500,
        quality_tier="balanced",
        request_id="shadow-balanced-001",
        force_shadow=False,
    )

    lines = _wait_for_lines(log_path, min_lines=1)
    assert len(lines) == 1


def test_shadow_summary_endpoint(tmp_path: Path, monkeypatch) -> None:
    log_path = _configure_paths(tmp_path, monkeypatch)

    row = {
        "request_id": "summary-001",
        "timestamp": "2026-01-01T00:00:00Z",
        "primary_model": "vllm",
        "shadow_model": "openai",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "primary_latency_ms": 300.0,
        "shadow_latency_ms": 420.0,
        "primary_response": "same",
        "shadow_response": "same",
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    response = client.get("/eval/shadow-summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["agreement_rate"] == 1.0
    assert payload["avg_latency_delta_ms"] == 120.0
    assert payload["avg_cost_delta"] > 0
