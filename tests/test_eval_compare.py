import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app.eval.compare import compare_routed_models
from backend.app.main import app


client = TestClient(app)


def test_compare_routed_models_has_jsonl_compatible_fields() -> None:
    result = compare_routed_models(
        prompt="Summarize this policy.",
        models=["baseline", "fast", "eval"],
    )

    assert result["prompt"] == "Summarize this policy."
    assert len(result["comparisons"]) == 3

    for row in result["comparisons"]:
        assert row["prompt"] == "Summarize this policy."
        assert "model" in row
        assert "answer" in row
        assert "response" in row
        assert isinstance(row["latency_ms"], float)
        assert isinstance(row["tokens_generated"], int)


def test_eval_compare_endpoint() -> None:
    response = client.post(
        "/v1/eval/compare",
        json={
            "prompt": "ping",
            "models": ["baseline", "fast", "eval"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prompt"] == "ping"
    assert len(payload["comparisons"]) == 3
    assert {row["model"] for row in payload["comparisons"]} == {
        "baseline",
        "fast",
        "eval",
    }
