import json, os, time
from pathlib import Path
import pytest

from saas.operations import cleanup_backup_artifacts, recovery_measurement, journal_integrity_report, acquire_maintenance_lock, release_maintenance_lock
from saas.postgres_repository import connect, migrate
from saas.lifecycle import DeletionJournal

pytestmark = pytest.mark.postgres_integration


def test_maintenance_cleanup_is_dry_run_by_default_and_protects_active_artifacts(tmp_path):
    old = tmp_path / "old.enc"; old.write_bytes(b"synthetic")
    os.utime(old, (time.time() - 1000, time.time() - 1000))
    (tmp_path / "old.enc.json").write_text(json.dumps({"encrypted": True}))
    events = cleanup_backup_artifacts(tmp_path, max_age_seconds=100, protected=[old])
    assert events[0]["reason"] == "protected" and old.exists()
    events = cleanup_backup_artifacts(tmp_path, max_age_seconds=100, execute=True, protected=[old])
    assert events[0]["reason"] == "protected" and old.exists()
    old.unlink(); old.with_suffix(old.suffix + ".json").unlink()
    old.write_bytes(b"synthetic"); os.utime(old, (time.time() - 1000, time.time() - 1000))
    assert cleanup_backup_artifacts(tmp_path, max_age_seconds=100, execute=True)[0]["action"] == "deleted"
    assert not old.exists()


def test_recovery_measurement_reports_observed_values_and_never_production_guarantee():
    report = recovery_measurement(100.0, 103.0, 107.0, 99.0, rto_objective_seconds=10, max_recovery_point_age_seconds=5)
    assert report["observed"]["total_seconds"] == 7.0
    assert report["within_objectives"] is True and report["production_guarantee"] is False


def test_journal_integrity_and_postgres_maintenance_lock(monkeypatch, tmp_path):
    if not os.getenv("AGENTTRUST_POSTGRES_URL"):
        pytest.fail("Gate 22E requires disposable PostgreSQL; refusing to skip")
    journal = DeletionJournal(tmp_path / "deletions.jsonl")
    journal.append("synthetic-org", "synthetic-operator")
    assert journal_integrity_report(journal)["count"] == 1
    migrate()
    with connect() as conn:
        assert acquire_maintenance_lock(conn, "recovery-drill")
        assert release_maintenance_lock(conn, "recovery-drill") is None

