from __future__ import annotations

import importlib
from urllib import error

from providers.vllm_provider import VLLMProvider


def test_vllm_provider_uses_openai_chat_completions_endpoint() -> None:
    provider = VLLMProvider(base_url="http://localhost:8000")
    assert provider.endpoint == "http://localhost:8000/v1/chat/completions"


def test_vllm_provider_falls_back_to_mock_when_unavailable(monkeypatch) -> None:
    provider = VLLMProvider(base_url="http://localhost:8000")

    def _fail_post(_payload):
        raise error.URLError("unavailable")

    monkeypatch.setattr(provider, "_post", _fail_post)

    result = provider.generate("hello")

    assert result["output"] == "mock response"
    assert result["tokens_out"] == 20
    assert result["latency_ms"] == 50


def test_router_uses_vllm_provider_when_provider_env_set(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER", "vllm")

    import backend.app.router as router_module

    importlib.reload(router_module)

    assert isinstance(router_module.ROUTER["openai"], VLLMProvider)
    assert isinstance(router_module.ROUTER["vllm"], VLLMProvider)
