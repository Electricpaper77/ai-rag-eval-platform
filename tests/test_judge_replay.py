from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from scripts import judge_replay


REQUIRED_FIELDS = {
    "timestamp",
    "question",
    "retrieved_docs",
    "answer",
    "citations",
    "deterministic_scores",
    "gemini_enabled",
    "gemini_model",
    "final_decision",
    "latency_ms",
    "notes",
}


def test_replay_writes_required_jsonl_without_gemini_key(tmp_path, monkeypatch):
    output_path = tmp_path / "judge_replay.jsonl"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["judge_replay.py", "--output", str(output_path)])

    assert judge_replay.main() == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))

    assert REQUIRED_FIELDS <= written.keys()
    assert written["gemini_enabled"] is False
    assert written["gemini_model"] is None
    assert written["final_decision"] == "pass"
    assert written["citations"] == [doc["source_id"] for doc in written["retrieved_docs"]]
    assert written["deterministic_scores"]["final_recommendation"] == "pass"


def test_replay_gemini_path_is_optional_and_mocked(tmp_path):
    output_path = tmp_path / "judge_replay_gemini.jsonl"
    calls: list[dict] = []

    def generate_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            response_id="mocked-judge-replay",
            model_version="mocked-model-version",
            usage_metadata=None,
            parsed={
                "groundedness_score": 0.99,
                "citation_support_score": 0.99,
                "hallucination_risk_score": 0.01,
                "pii_exposure_risk_score": 0.0,
                "prompt_injection_risk_score": 0.0,
                "final_recommendation": "pass",
                "explanation": "Mocked Gemini assessment for CI.",
                "concerns": [],
            },
        )

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    record = judge_replay.run_replay(
        output_path,
        api_key="mock-key-not-secret",
        model="gemini-mocked-model",
        client=client,
    )

    assert len(calls) == 1
    assert calls[0]["model"] == "gemini-mocked-model"
    assert record["gemini_enabled"] is True
    assert record["gemini_model"] == "gemini-mocked-model"
    assert record["final_decision"] == "pass"
    assert Path(output_path).is_file()
