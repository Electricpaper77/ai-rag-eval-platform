import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_query_guarded_endpoint():

    response = client.post(
        "/query_guarded",
        json={
            "question":"ping",
            "top_k":1
        }
    )

    assert response.status_code == 200


def test_metrics_endpoint():

    response = client.get("/metrics")

    assert response.status_code == 200


def test_evaluate_endpoint():

    response = client.post(
        "/evaluate",
        json={
            "prompt":"ping"
        }
    )

    assert response.status_code == 200



def test_openai_wrapper():

    response = client.post(
        "/v1/chat/completions",
        json={
            "messages":[
                {"role":"user","content":"ping"}
            ]
        }
    )

    assert response.status_code == 200

