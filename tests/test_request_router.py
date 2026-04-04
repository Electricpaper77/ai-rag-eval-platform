from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app
import gpu_platform.request_router as request_router
import gpu_platform.router_policies as router_policies
import gpu_platform.shadow_eval as shadow_eval


client = TestClient(app)


def _configure_paths(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    jobs_dir = tmp_path / "artifacts" / "platform_jobs"
    proof_dir = tmp_path / "artifacts" / "proof"
    decisions_path = jobs_dir / "routing_decisions.jsonl"
    shadow_path = proof_dir / "shadow_eval_summary.json"

    monkeypatch.setattr(request_router, "ROUTING_DECISIONS_PATH", decisions_path)
    monkeypatch.setattr(shadow_eval, "SHADOW_SUMMARY_PATH", shadow_path)

    eval_summary_path = proof_dir / "eval_dashboard_summary.json"
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
                    {
                        "run_id": "mock_primary",
                        "pass_rate": 0.7,
                        "hallucination_rate": 0.2,
                        "p95_latency_ms": 200,
                        "tokens_per_sec_avg": 20,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(router_policies, "EVAL_SUMMARY_PATH", eval_summary_path)

    request_router.PREFIX_CACHE.clear()
    return decisions_path, shadow_path


def test_router_selects_backend_and_returns_score(tmp_path: Path, monkeypatch) -> None:
    decisions_path, _ = _configure_paths(tmp_path, monkeypatch)

    response = client.post(
        "/platform/chat",
        json={
            "messages": [{"role": "system", "content": "You are helpful"}, {"role": "user", "content": "hello"}],
            "latency_budget_ms": 1500,
            "quality_tier": "balanced",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["selected_backend"] in {"vllm", "openai", "mock"}
    assert "routing_score" in body
    assert decisions_path.exists()


def test_repeated_prefix_adds_vllm_preference(tmp_path: Path, monkeypatch) -> None:
    _configure_paths(tmp_path, monkeypatch)

    messages = [
        {"role": "system", "content": "Repeated system prompt"},
        {"role": "user", "content": "Question A"},
    ]

    first = request_router.route_request(messages, latency_budget_ms=1200, quality_tier="balanced")
    second = request_router.route_request(messages, latency_budget_ms=1200, quality_tier="balanced")

    assert first["cache_hint_used"] is False
    assert second["cache_hint_used"] is True
    assert second["selected_backend"] == "vllm"


def test_shadow_eval_summary_created(tmp_path: Path, monkeypatch) -> None:
    _, shadow_path = _configure_paths(tmp_path, monkeypatch)

    request_router.route_request(
        messages=[{"role": "system", "content": "shadow"}, {"role": "user", "content": "test"}],
        latency_budget_ms=1200,
        quality_tier="balanced",
        request_id="shadow-request-001",
        force_shadow=True,
    )

    assert shadow_path.exists()
    payload = json.loads(shadow_path.read_text(encoding="utf-8"))
    assert payload["total_comparisons"] >= 1
