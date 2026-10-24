import hashlib
import json

import pytest


def test_case_investigation_reports_missing_evidence_without_inference(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_BACKEND", "sqlite")
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", str(tmp_path / "gate23d.sqlite3"))
    from saas.repository import connect
    from saas.investigation import list_cases

    conn = connect()
    conn.execute("INSERT INTO organizations VALUES (?,?,?)", ("org_contract", "Contract", "2026-01-01T00:00:00+00:00"))
    conn.execute("INSERT INTO memberships VALUES (?,?,?,?)", ("org_contract", "user_contract", "owner", "2026-01-01T00:00:00+00:00"))
    conn.execute("INSERT INTO projects VALUES (?,?,?,?)", ("prj_contract", "org_contract", "Project", "2026-01-01T00:00:00+00:00"))
    conn.execute("INSERT INTO evaluation_runs VALUES (?,?,?,?,?,?,?,?)", ("run_contract", "org_contract", "prj_contract", "idem_contract", "completed", "mock", 1, "2026-01-01T00:00:00+00:00"))
    conn.commit(); conn.close()

    result = list_cases("org_contract", "prj_contract", "run_contract", "user_contract")
    assert result["evidence_status"] == "MISSING_EVIDENCE"
    assert result["cases"] == []
    assert "persisted per-case evidence" in result["message"]


def test_review_revision_is_append_only_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_BACKEND", "sqlite")
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", str(tmp_path / "gate23d.sqlite3"))
    from saas.repository import connect
    from saas.investigation import create_case_review, list_case_reviews

    conn = connect()
    ts = "2026-01-01T00:00:00+00:00"
    conn.execute("INSERT INTO organizations VALUES (?,?,?)", ("org_review", "Review", ts))
    conn.execute("INSERT INTO memberships VALUES (?,?,?,?)", ("org_review", "user_review", "owner", ts))
    conn.execute("INSERT INTO projects VALUES (?,?,?,?)", ("prj_review", "org_review", "Project", ts))
    conn.execute("INSERT INTO evaluation_runs VALUES (?,?,?,?,?,?,?,?)", ("run_review", "org_review", "prj_review", "idem_review", "completed", "mock", 1, ts))
    evidence = {"source": "synthetic_test_case", "citation": "fixture-only"}
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    conn.execute("INSERT INTO evaluation_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("case_review", "org_review", "prj_review", "run_review", "case-1", "failed", "groundedness", 0.1, json.dumps(evidence), digest, "synthetic_test", ts))
    conn.commit(); conn.close()

    first = create_case_review("case_review", "org_review", "user_review", "confirmed", "Reviewer confirmed the persisted fixture evidence.", 0, "review-once")
    replay = create_case_review("case_review", "org_review", "user_review", "confirmed", "ignored on replay", 0, "review-once")
    assert first["id"] == replay["id"]
    assert first["provenance"] == "reviewer_confirmed"
    assert first["reviewer_id"] == "user_review"
    assert len(list_case_reviews("case_review", "org_review", "user_review")) == 1

    with pytest.raises(ValueError, match="revision conflict"):
        create_case_review("case_review", "org_review", "user_review", "hold", "stale revision", 0, "review-two")

