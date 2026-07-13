from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes import agenttrust_demo


app = FastAPI()
app.include_router(agenttrust_demo.router)
client = TestClient(app)


def test_agenttrust_iq_demo_returns_full_deterministic_flow(tmp_path, monkeypatch):
    audit_path = tmp_path / "demo_runs.jsonl"
    monkeypatch.setattr(agenttrust_demo, "AUDIT_LOG_PATH", audit_path)

    response = client.get("/demo/agenttrust-iq")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == "AgentTrust IQ"
    assert payload["track"] == "Reasoning Agents"
    assert payload["agent_readiness_score"] == 92
    assert payload["failure_reasons"] == []
    assert payload["recommended_fixes"] == []
    assert [item["source_id"] for item in payload["retrieved_evidence"]] == [
        "source_1",
        "source_2",
        "source_3",
    ]
    assert "[source_1]" in payload["agent_answer"]
    assert "[source_2]" in payload["agent_answer"]
    assert "[source_3]" in payload["agent_answer"]
    assert payload["checks"] == {
        "groundedness": "pass",
        "citation_support": "pass",
        "hallucination_risk": "low",
        "prompt_injection_resistance": "pass",
        "pii_exposure": "none",
        "latency_ms": 12.0,
        "audit_log_complete": "pass",
    }
    assert [item["tool_tier"] for item in payload["tool_tier_examples"]] == [
        "read-only / recon",
        "read-only / recon",
        "destructive / irreversible",
    ]
    assert payload["tool_tier_examples"][0]["human_approval_gate"] == "not_required"
    assert payload["tool_tier_examples"][2]["human_approval_gate"] == "required"

    returned_record = json.loads(payload["jsonl_audit_record"])
    written_record = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert returned_record == written_record
    assert written_record["demo_mode"] == "deterministic"
    assert written_record["run_id"] == "agenttrust-demo-001"
    assert written_record["timestamp"] == "2026-06-13T00:00:00Z"
    assert written_record["agent_readiness_score"] == 92


def test_agenttrust_iq_command_center_renders_judge_workflow():
    response = client.get("/demo/agenttrust-iq/command-center")

    assert response.status_code == 200
    assert "Controlled reliability demo" in response.text
    assert "AgentTrust IQ: AI Agent Reliability and Evaluation" in response.text
    assert "model-agnostic AI agent reliability and evaluation platform" in response.text
    assert "Optional Gemini integration" in response.text
    assert "View GitHub Proof" in response.text
    assert "AgentTrust IQ Fits a Model-Agnostic Release Pipeline" in response.text
    assert "customer-production telemetry" in response.text
    assert "Microsoft" not in response.text
    assert "Not Another Agent. The Trust Layer for Agents." in response.text
    assert "Produces replayable JSONL audit logs" in response.text
    assert "Deployment Decision: APPROVE WITH AUDIT EVIDENCE" in response.text
    assert "Retrieved Evidence" in response.text
    assert "Cited Agent Answer" in response.text
    assert "Deployment Decision" in response.text
    assert "JSONL Audit Record" in response.text
    assert "/demo/agenttrust-iq" in response.text
