from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(autouse=True)
def proof_artifact_seed(tmp_path):
    """Seed deterministic proof artifacts expected by legacy artifact tests."""
    (tmp_path / "opentelemetry_pipeline.json").write_text(
        '{"otlp_exporter_enabled": false, "collector_config": "local-jsonl"}\n',
        encoding="utf-8",
    )


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def chat_payload():
    return {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Explain inference routing in one sentence."}],
        "max_tokens": 64,
    }
