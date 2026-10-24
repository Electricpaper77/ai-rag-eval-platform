import json

import pytest

from saas.decision_engine import evaluate
from saas.repository import create_decision, create_org, create_policy, create_project, create_run


def _policy():
    return {
        "id": "pol_1",
        "version": 1,
        "metrics_json": json.dumps({"quality": {"direction": "higher_is_better", "threshold": 0.8, "tolerance": 0.05, "unit": "score", "accepted_provenance": ["independently_computed"]}}),
        "require_baseline": True,
    }


def _run(run_id, value):
    return {"id": run_id, "result_json": json.dumps({"quality_metrics": {"quality": value}, "quality_metrics_provenance": {"quality": "independently_computed"}})}


def test_decision_pass_uses_recorded_metric_and_delta():
    decision, rationale, refs = evaluate(_policy(), _run("current", 0.90), _run("baseline", 0.85))
    assert decision == "PASS"
    assert rationale["observations"]["quality"]["delta"] == pytest.approx(0.05)
    assert refs["baseline_run_id"] == "baseline"


def test_decision_hold_reports_threshold_or_regression():
    decision, rationale, _ = evaluate(_policy(), _run("current", 0.70), _run("baseline", 0.90))
    assert decision == "HOLD"
    assert "quality" in rationale["threshold_failures"]
    assert "quality" in rationale["regressions"]


def test_missing_evidence_never_passes():
    decision, rationale, _ = evaluate(_policy(), {"id": "current", "result_json": "{}"}, _run("baseline", 0.9))
    assert decision == "INSUFFICIENT_EVIDENCE"
    assert rationale["missing_current_metrics"] == ["quality"]


def test_user_supplied_and_nonfinite_metrics_never_pass_without_authorized_provenance():
    user_supplied = {"id": "current", "result_json": json.dumps({"quality_metrics": {"quality": 0.99}, "quality_metrics_provenance": {"quality": "user_supplied"}})}
    decision, rationale, _ = evaluate(_policy(), user_supplied, _run("baseline", 0.9))
    assert decision == "INSUFFICIENT_EVIDENCE"
    assert rationale["untrusted_current_metrics"] == ["quality"]
    nonfinite = {"id": "current", "result_json": '{"quality_metrics":{"quality":NaN}}'}
    decision, rationale, _ = evaluate(_policy(), nonfinite, _run("baseline", 0.9))
    assert decision == "INSUFFICIENT_EVIDENCE"
    assert rationale["missing_current_metrics"] == ["quality"]


def test_sqlite_adapter_persists_versioned_policy_and_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_BACKEND", "sqlite")
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", str(tmp_path / "decision.sqlite3"))
    org = create_org("sqlite-user", "SQLite Decision Org")
    project = create_project(org["id"], "sqlite-user", "Project")
    baseline = create_run(org["id"], "sqlite-user", project["id"], "sqlite-baseline", [{"recorded_metrics": {"quality": 0.85}}], 100)["id"]
    current = create_run(org["id"], "sqlite-user", project["id"], "sqlite-current", [{"recorded_metrics": {"quality": 0.9}}], 100)["id"]
    policy = create_policy(org["id"], project["id"], "sqlite-user", {"name": "sqlite-policy", "metrics": {"quality": {"direction": "higher_is_better", "threshold": 0.8, "tolerance": 0.05, "accepted_provenance": ["synthetic_test"]}}, "require_baseline": True})
    decision = create_decision(org["id"], current, "sqlite-user", {"policy_id": policy["id"], "baseline_run_id": baseline, "idempotency_key": "sqlite-decision"})
    assert decision["decision"] == "PASS"


def test_synthetic_policy_is_rejected_outside_isolated_test_deployment(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_BACKEND", "sqlite")
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", str(tmp_path / "boundary.sqlite3"))
    monkeypatch.setenv("AGENTTRUST_DEPLOYMENT_POLICY", "production")
    org = create_org("boundary-user", "Boundary Org")
    project = create_project(org["id"], "boundary-user", "Project")
    with pytest.raises(ValueError, match="synthetic_test provenance"):
        create_policy(org["id"], project["id"], "boundary-user", {"name": "synthetic-policy", "metrics": {"quality": {"direction": "higher_is_better", "threshold": 0.8, "accepted_provenance": ["synthetic_test"]}}})
