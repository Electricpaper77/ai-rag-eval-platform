from __future__ import annotations

from backend.app import main


def test_api_key_auth_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AGENTTRUST_REQUIRE_API_KEY", raising=False)

    assert main._api_key_auth_enabled() is False


def test_api_key_header_validation(monkeypatch) -> None:
    monkeypatch.setenv("AGENTTRUST_API_KEY", "test-key")

    assert main._request_has_valid_api_key({"x-agenttrust-api-key": "test-key"})
    assert main._request_has_valid_api_key({"authorization": "Bearer test-key"})
    assert not main._request_has_valid_api_key({"x-agenttrust-api-key": "wrong"})
    assert not main._request_has_valid_api_key({})


def test_production_public_path_scope() -> None:
    assert "/health" in main.PUBLIC_PRODUCTION_PATHS
    assert "/metrics" not in main.PUBLIC_PRODUCTION_PATHS
    assert "/evaluate" not in main.PUBLIC_PRODUCTION_PATHS
    assert "/dashboard/evidence" not in main.PUBLIC_PRODUCTION_PATHS


def test_production_auth_decision_allows_health_without_key(monkeypatch) -> None:
    monkeypatch.setenv("AGENTTRUST_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("AGENTTRUST_API_KEY", "test-key")

    assert not main._should_require_api_key("GET", "/health", {})


def test_production_auth_decision_blocks_protected_routes_without_key(monkeypatch) -> None:
    monkeypatch.setenv("AGENTTRUST_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("AGENTTRUST_API_KEY", "test-key")

    assert main._should_require_api_key("GET", "/metrics", {})
    assert main._should_require_api_key("POST", "/evaluate", {})
    assert main._should_require_api_key("GET", "/openapi.json", {})


def test_production_auth_decision_allows_protected_routes_with_bearer_key(monkeypatch) -> None:
    monkeypatch.setenv("AGENTTRUST_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("AGENTTRUST_API_KEY", "test-key")

    assert not main._should_require_api_key("POST", "/evaluate", {"authorization": "Bearer test-key"})
    assert not main._should_require_api_key("GET", "/metrics", {"x-agenttrust-api-key": "test-key"})


def test_production_auth_decision_allows_options_preflight(monkeypatch) -> None:
    monkeypatch.setenv("AGENTTRUST_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("AGENTTRUST_API_KEY", "test-key")

    assert not main._should_require_api_key("OPTIONS", "/evaluate", {})
