from pathlib import Path

import pytest


def test_demo_pack_and_completed_run_are_traceable(client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from backend.app.routes import recruiter_golden_path as route
    monkeypatch.setattr(route, "RUN_DIR", tmp_path)
    route._state.update(status="ready", run=None, error=None)
    pack = client.get("/api/recruiter-golden-path/pack").json()
    assert pack["case_count"] == 6 and pack["mode"] == "no-key controlled fixture"
    result = client.post("/api/recruiter-golden-path/run")
    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] == "completed"
    assert payload["scorecard"]["total_cases"] == 6
    assert payload["scorecard"]["passed_cases"] + payload["scorecard"]["failed_cases"] == 6
    assert payload["verdict"]["value"] == "PASS"
    assert payload["evidence"]["run_id"] == "recruiter-golden-path"
    assert client.get("/api/recruiter-golden-path/evidence/results.jsonl").status_code == 200


def test_failures_and_duplicate_or_backend_error_are_truthful(client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from backend.app.routes import recruiter_golden_path as route
    monkeypatch.setattr(route, "RUN_DIR", tmp_path)
    route._state.update(status="ready", run=None, error=None)
    assert route._verdict([{"pass": False, "failure_reasons": ["citation coverage: missing citation"]}])[0] == "BLOCK"
    assert "secret" not in client.get("/recruiter-golden-path").text.lower()
    assert route._lock.acquire(blocking=False)
    try:
        assert client.post("/api/recruiter-golden-path/run").status_code == 409
    finally:
        route._lock.release()
    def boom(*args, **kwargs): raise RuntimeError("api_key=never-render")
    monkeypatch.setattr(route, "run_eval_harness", boom)
    assert client.post("/api/recruiter-golden-path/run").status_code == 500
    assert client.get("/api/recruiter-golden-path/run").json()["status"] == "failed"
