from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.main import app


client = TestClient(app)


def test_chat_completions_returns_openai_schema(monkeypatch):
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-llm",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ],
            "max_tokens": 64,
            "temperature": 0.7,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["object"] == "chat.completion"
    assert data["model"] == "mock-llm"
    assert isinstance(data["created"], int)
    assert isinstance(data["id"], str)
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "content" in data["choices"][0]["message"]

    usage = data["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
