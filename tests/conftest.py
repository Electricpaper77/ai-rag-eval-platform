from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path)
    return TestClient(app)


@pytest.fixture()
def chat_payload():
    return {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Explain inference routing in one sentence."}],
        "max_tokens": 64,
    }

