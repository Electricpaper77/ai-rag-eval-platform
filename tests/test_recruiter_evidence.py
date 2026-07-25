import json
from pathlib import Path

import pytest

from app.eval.run import load_suite, redact_secrets, run_evaluation, suite_sha256


def test_deterministic_evidence_and_hash(tmp_path: Path) -> None:
    suite = Path("eval/nvidia_nemotron_pack.jsonl")
    first = run_evaluation(suite, tmp_path / "one")
    second = run_evaluation(suite, tmp_path / "two")
    assert first["total_cases"] == 50
    assert first["suite_sha256"] == suite_sha256(suite) == second["suite_sha256"]
    assert first["benchmark_status"] == "mock"
    assert first["git_commit_sha"]
    assert json.loads((tmp_path / "one" / "run_manifest.json").read_text())["contains_secrets"] is False


def test_empty_malformed_and_secret_redaction(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"; empty.write_text("")
    malformed = tmp_path / "bad.jsonl"; malformed.write_text("not json\n")
    with pytest.raises(ValueError, match="empty"):
        load_suite(empty)
    with pytest.raises(ValueError, match="Invalid JSONL"):
        load_suite(malformed)
    assert redact_secrets("api_key=top-secret") == "[REDACTED]"


def test_downloadable_evidence_and_missing_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.routes import recruiter_evidence
    from fastapi import HTTPException

    monkeypatch.setattr(recruiter_evidence, "EVIDENCE_DIR", tmp_path)
    with pytest.raises(HTTPException) as missing:
        recruiter_evidence.recruiter_evidence_summary()
    assert missing.value.status_code == 404
    run_evaluation(Path("eval/nvidia_nemotron_pack.jsonl"), tmp_path)
    assert recruiter_evidence.recruiter_evidence_summary()["benchmark_status"] == "mock"
    assert str(recruiter_evidence.download_evidence("summary.json").path).endswith("summary.json")
    with pytest.raises(HTTPException):
        recruiter_evidence.download_evidence("not-allowed.json")
