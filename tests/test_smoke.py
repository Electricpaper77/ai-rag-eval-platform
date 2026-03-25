import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_chat_endpoint_exists():

    response = client.post(
        "/v1/chat/completions",
        json={
            "messages":[
                {"role":"user","content":"ping"}
            ]
        }
    )

    assert response.status_code in [200,422]


def test_metrics_endpoint_exists():

    response = client.get("/metrics")

    assert response.status_code == 200


def test_health_endpoint_exists():

    response = client.get("/")

    assert response.status_code == 200

