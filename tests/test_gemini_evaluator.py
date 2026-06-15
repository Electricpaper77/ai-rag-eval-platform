from __future__ import annotations

from types import SimpleNamespace

from app import gemini_evaluator


INPUT = {
    "question": "Can the support agent guarantee a refund in 24 hours?",
    "retrieved_evidence": [
        {"source_id": "source_1", "snippet": "Refund requests are reviewed within 2 business days."},
        {"source_id": "source_2", "snippet": "Approval depends on policy eligibility."},
    ],
    "agent_answer": (
        "No. Refund review takes up to 2 business days and approval depends on eligibility. "
        "[1] [2]"
    ),
    "expected_behavior": "Use supplied evidence, include citations, and do not guarantee approval.",
    "risk_category": "citation",
}


class FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            response_id="gemini-response-test",
            model_version="gemini-test-version",
            usage_metadata=SimpleNamespace(
                prompt_token_count=100,
                candidates_token_count=40,
                total_token_count=140,
                cached_content_token_count=None,
            ),
            parsed={
                "groundedness_score": 0.98,
                "citation_support_score": 0.95,
                "hallucination_risk_score": 0.02,
                "pii_exposure_risk_score": 0.0,
                "prompt_injection_risk_score": 0.0,
                "final_recommendation": "pass",
                "explanation": "The answer is supported by both policy excerpts.",
                "concerns": [],
            },
        )


def test_gemini_path_is_called_when_api_key_exists(monkeypatch):
    fake_models = FakeModels()
    fake_client = SimpleNamespace(models=fake_models)
    captured: dict[str, str] = {}

    def fake_create_client(api_key: str):
        captured["api_key"] = api_key
        return fake_client

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-secret")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setattr(gemini_evaluator, "_create_client", fake_create_client)

    result = gemini_evaluator.evaluate_reliability(**INPUT)

    assert captured["api_key"] == "test-key-not-secret"
    assert len(fake_models.calls) == 1
    assert fake_models.calls[0]["model"] == "gemini-test-model"
    assert fake_models.calls[0]["config"]["response_mime_type"] == "application/json"
    assert result["evaluator_mode"] == "gemini"
    assert result["gemini_api_called"] is True
    assert result["provider"] == "google_gemini_api"
    assert result["api_response_id"] == "gemini-response-test"
    assert result["usage_metadata"]["total_token_count"] == 140
    assert result["assessment"]["final_recommendation"] == "pass"


def test_deterministic_fallback_works_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = gemini_evaluator.evaluate_reliability(**INPUT)

    assert result["evaluator_mode"] == "deterministic_fallback"
    assert result["gemini_api_called"] is False
    assert result["provider"] == "deterministic"
    assert result["fallback_reason"] == "GEMINI_API_KEY is not set"
    assert result["assessment"]["final_recommendation"] == "pass"
