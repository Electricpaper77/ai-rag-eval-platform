from backend.app.inference import handle_chat_completions
from backend.app.router import ROUTER


def _request(model: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "hello world"}],
    }


def test_router_supports_required_models() -> None:
    for model_name in ("openai", "mock"):
        assert model_name in ROUTER


def test_chat_completions_routes_to_mock_runtime() -> None:
    response = handle_chat_completions(_request("mock"))
    assert response["id"] == "chatcmpl-mock"
    assert response["choices"][0]["message"]["content"] == "mock response"
    assert response["tokens_out"] == 20
    assert response["model_runtime"] == "mock"


def test_unknown_model_falls_back_to_mock() -> None:
    response = handle_chat_completions(_request("unknown-model"))
    assert response["id"] == "chatcmpl-mock"
    assert response["choices"][0]["message"]["content"] == "mock response"


def test_legacy_model_alias_still_works() -> None:
    response = handle_chat_completions(_request("baseline"))
    assert response["id"] == "chatcmpl-baseline"
    assert response["choices"][0]["message"]["content"] == "mock response"
