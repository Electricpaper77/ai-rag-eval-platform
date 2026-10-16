import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import backend.app.main as main_module
from backend.app.main import app, create_app

client = TestClient(app)


def _route_paths(routes):
    paths = set()
    for route in routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        elif hasattr(route, "routes"):
            paths.update(_route_paths(route.routes))
        elif hasattr(route, "original_router"):
            paths.update(_route_paths(route.original_router.routes))
        else:
            raise AssertionError(f"unsupported route object: {type(route)!r}")
    return paths


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


def test_create_app_matches_deployed_app():
    created = create_app()
    created_paths = _route_paths(created.routes)
    deployed_paths = _route_paths(app.routes)

    assert "/evaluate" in created_paths
    assert created_paths == deployed_paths


def test_evaluate_endpoint(tmp_path, monkeypatch):
    eval_log = tmp_path / "runs.jsonl"
    monkeypatch.setattr(main_module, "EVAL_RESULTS_PATH", eval_log)

    response = client.post(
        "/evaluate",
        json={
            "prompt": "Summarize the refund policy and cite the source.",
            "model_response": "Refunds are available within 30 days. [1]",
            "expected_behavior": "Answer the refund policy with a citation.",
            "risk_category": "rag_quality",
            "metadata": {"citations": [{"source": "refund_policy.txt"}]},
        }
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) >= {"pass", "score", "failure_reasons", "metrics", "run_id"}
    assert set(payload["metrics"]) == {
        "hallucination_risk",
        "citation_coverage",
        "refusal_accuracy",
        "pii_leakage",
        "prompt_injection_compliance",
    }
    assert eval_log.exists()
    assert payload["run_id"] in eval_log.read_text(encoding="utf-8")



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
