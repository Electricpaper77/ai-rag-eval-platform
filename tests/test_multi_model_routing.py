from backend.app.inference import handle_chat_completions
from backend.app.routing.router import DEFAULT_ROUTER


def _request(model: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "hello world"}],
    }


def test_router_supports_required_models() -> None:
    for model_name in ("baseline", "fast", "eval"):
        resolved, _ = DEFAULT_ROUTER.resolve_backend(model_name)
        assert resolved == model_name


def test_chat_completions_routes_to_fast_backend() -> None:
    response = handle_chat_completions(_request("fast"))
    assert response["id"] == "chatcmpl-fast"
    assert "optimized backend response" in response["choices"][0]["message"]["content"]


def test_unknown_model_falls_back_to_baseline() -> None:
    response = handle_chat_completions(_request("unknown-model"))
    assert response["id"] == "chatcmpl-baseline"
    assert "baseline backend response" in response["choices"][0]["message"]["content"]
