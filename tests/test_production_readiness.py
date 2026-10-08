from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_health_metrics_and_openapi_are_available(client) -> None:
    health = client.get("/health")
    metrics = client.get("/metrics")
    openapi = client.get("/openapi.json")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert metrics.status_code == 200
    assert "text/plain" in metrics.headers["content-type"]
    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "AI RAG Eval Platform"


def test_invalid_chat_request_returns_400_not_500(client) -> None:
    response = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini"})

    assert response.status_code == 400
    assert "messages field required" in response.json()["detail"]


def test_environment_example_documents_runtime_knobs() -> None:
    env_text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for key in (
        "OPENAI_API_KEY=",
        "GEMINI_API_KEY=",
        "GEMINI_MODEL=",
        "MODEL_NAME=",
        "VECTOR_DB=",
        "PORT=",
        "INFERENCE_BACKEND=",
        "EVAL_ARTIFACT_DIR=",
    ):
        assert key in env_text


def test_deployment_configs_reference_backend_app() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    procfile = (REPO_ROOT / "backend" / "Procfile").read_text(encoding="utf-8")
    cloudbuild = (REPO_ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")

    assert "gunicorn backend.app.main:app" in dockerfile
    assert "uvicorn backend.app.main:app" in procfile
    assert "docker" in cloudbuild
    assert "rag-eval-repo/api:ci-test" in cloudbuild


def test_dockerignore_excludes_runtime_artifacts_and_secrets() -> None:
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    entries = {line.strip() for line in dockerignore if line.strip() and not line.startswith("#")}

    assert ".git" in entries
    assert ".env" in entries
    assert "artifacts" in entries
    assert "runs" in entries
    assert "docs/artifacts" in entries
    assert "__pycache__" in entries
    assert "!.env.example" in entries


def test_vercel_config_is_static_frontend_only() -> None:
    config = json.loads((REPO_ROOT / "vercel.json").read_text(encoding="utf-8"))
    destinations = {rewrite["destination"] for rewrite in config["rewrites"]}

    assert "/frontend/index.html" in destinations
    assert "/frontend/agenttrust-iq-command-center.html" in destinations
    assert all("backend.app.main" not in destination for destination in destinations)
