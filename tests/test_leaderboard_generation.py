from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_run_model_eval_generates_leaderboard_and_endpoint_reads_it(tmp_path: Path) -> None:
    dataset = tmp_path / "prompts.jsonl"
    dataset.write_text(
        "\n".join([
            json.dumps({"prompt": "Summarize policy A"}),
            json.dumps({"prompt": "What is retrieval-augmented generation?"}),
            json.dumps({"prompt": "Explain GPU scheduling"}),
        ]),
        encoding="utf-8",
    )

    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """
models:
  - id: model_a
    provider: mock
    quality_score: 0.78
    avg_latency_ms: 450
    cost_per_1k_tokens: 0.11
  - id: model_b
    provider: mock
    quality_score: 0.88
    avg_latency_ms: 780
    cost_per_1k_tokens: 0.20
""",
        encoding="utf-8",
    )

    output_dir = tmp_path / "model_eval"
    cmd = [
        sys.executable,
        "scripts/run_model_eval.py",
        "--dataset",
        str(dataset),
        "--registry",
        str(registry),
        "--output-dir",
        str(output_dir),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    assert "leaderboard_path" in result.stdout

    leaderboard_path = output_dir / "leaderboard.json"
    assert leaderboard_path.exists()

    payload = json.loads(leaderboard_path.read_text(encoding="utf-8"))
    assert len(payload) == 2
    assert {row["model"] for row in payload} == {"model_a", "model_b"}
    assert all("pass_rate" in row for row in payload)


def test_leaderboard_endpoint_returns_json(tmp_path: Path, monkeypatch) -> None:
    leaderboard_path = tmp_path / "leaderboard.json"
    leaderboard_path.write_text(
        json.dumps([
            {
                "model": "demo-model",
                "pass_rate": 0.84,
                "hallucination_rate": 0.07,
                "p95_latency_ms": 990,
                "cost_per_request": 0.004,
            }
        ]),
        encoding="utf-8",
    )

    import backend.app.main as main_module

    monkeypatch.setattr(main_module, "LEADERBOARD_PATH", str(leaderboard_path))

    resp = client.get("/leaderboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["model"] == "demo-model"
