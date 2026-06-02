from __future__ import annotations

from app.models import ChatCompletionRequest


def test_openai_compatible_request_schema_accepts_extra_fields(chat_payload):
    payload = {**chat_payload, "temperature": 0.2, "top_p": 0.9}
    request = ChatCompletionRequest.model_validate(payload)
    assert request.model == "gpt-4o-mini"
    assert request.messages[0].role == "user"
    assert request.model_extra["top_p"] == 0.9


def test_chat_completions_returns_openai_style_response(client, chat_payload):
    response = client.post("/v1/chat/completions", json=chat_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["usage"]["total_tokens"] >= body["usage"]["completion_tokens"]
    assert body["backend"]


def test_chat_completions_streams_openai_style_sse_chunks(client, chat_payload):
    with client.stream("POST", "/v1/chat/completions", json={**chat_payload, "stream": True}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        text = "".join(response.iter_text())

    assert "chat.completion.chunk" in text
    assert '"delta":{"role":"assistant"}' in text
    assert '"delta":{"content":"' in text
    assert "data: [DONE]" in text


def test_health_works(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
