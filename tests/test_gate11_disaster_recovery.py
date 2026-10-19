from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from backend.app.recovery.models import records_checksum, state_is_valid
from backend.app.recovery.service import RecoveryService


ROOT = Path(__file__).resolve().parents[1]
RECOVERY_MANIFESTS = ROOT / "deploy" / "recovery"


def _env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "RECOVERY_PRIMARY_PATH": str(tmp_path / "primary" / "state.json"),
            "RECOVERY_BACKUP_PATH": str(tmp_path / "backup"),
            "RECOVERY_CONFIG_PATH": str(tmp_path / "config" / "recovery-config.json"),
        }
    )
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "recovery-config.json").write_text(
        '{"model_name":"agenttrust-mock","policy_version":"gate11-v1","routing_mode":"deterministic"}\n',
        encoding="utf-8",
    )
    return env


def test_seed_checkpoint_and_checksum_are_deterministic(tmp_path: Path):
    service = RecoveryService(tmp_path / "primary" / "state.json", tmp_path / "backup", tmp_path / "config.json")
    document = service.seed(20)
    assert len(document["records"]) == 20
    assert document["latest_sequence"] == 20
    assert document["checksum"] == records_checksum(document["records"])
    assert state_is_valid(document)


def test_backup_restore_and_corrupt_backup_are_rejected(tmp_path: Path):
    env = _env(tmp_path)
    service = RecoveryService(
        Path(env["RECOVERY_PRIMARY_PATH"]), Path(env["RECOVERY_BACKUP_PATH"]), Path(env["RECOVERY_CONFIG_PATH"])
    )
    service.seed(20)
    backup = subprocess.run(
        [sys.executable, "-m", "scripts.gate11_backup", "--backup-id", "backup-test"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert backup.returncode == 0, backup.stdout + backup.stderr
    service.append(3)
    service.corrupt()
    restored = subprocess.run(
        [sys.executable, "-m", "scripts.gate11_restore", "--backup-dir", env["RECOVERY_BACKUP_PATH"], "--backup-id", "backup-test"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert restored.returncode == 0, restored.stdout + restored.stderr
    status = service.status()
    assert status["status"] == "RECOVERED"
    assert status["record_count"] == 20
    assert status["latest_sequence"] == 20

    invalid = tmp_path / "invalid"
    shutil.copytree(Path(env["RECOVERY_BACKUP_PATH"]) / "backup-test", invalid)
    state_path = invalid / "state.json"
    state_path.write_text(state_path.read_text(encoding="utf-8").replace("recovery-0001", "tampered-0001"), encoding="utf-8")
    rejected = subprocess.run(
        [sys.executable, "-m", "scripts.gate11_restore", "--backup-dir", str(invalid), "--verify-only"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "RESTORE_REJECTED_CHECKSUM_MISMATCH" in rejected.stdout


def test_recovery_manifests_preserve_security_and_recovery_contract():
    resources = []
    for path in RECOVERY_MANIFESTS.glob("*.yaml"):
        resources.extend(item for item in yaml.safe_load_all(path.read_text(encoding="utf-8")) if item)
    deployment = next(item for item in resources if item.get("kind") == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    pod = deployment["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"] == {
        "runAsNonRoot": True,
        "runAsUser": 10001,
        "runAsGroup": 10001,
        "fsGroup": 10001,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["readinessProbe"]["httpGet"]["path"] == "/platform/recovery/status"
    assert container["livenessProbe"]["httpGet"]["path"] == "/healthz"
    env = {item["name"]: item["value"] for item in container["env"]}
    assert env["INFERENCE_BACKEND"] == "mock"
    assert env["AGENTTRUST_ARTIFACT_DIR"] == "/tmp/agenttrust_artifacts"
    assert env["INFERENCE_LOG_PATH"] == "/tmp/inference_runs.jsonl"
    assert {item["name"] for item in container["volumeMounts"]} >= {"primary-state", "backup-state", "tmp"}
    assert any(item.get("kind") == "PersistentVolumeClaim" for item in resources)
    rules = next(item for item in resources if item.get("metadata", {}).get("name") == "agenttrust-recovery-alert-rules")
    rule_text = rules["data"]["recovery-rules.yaml"]
    for alert in ("AgentTrustBackupStale", "AgentTrustRestoreFailed", "AgentTrustStateIntegrityFailure"):
        assert alert in rule_text


@pytest.mark.parametrize("path", ["/healthz", "/platform/recovery/status", "/platform/recovery/state", "/platform/recovery/checkpoint"])
def test_required_route_names_are_present(path: str):
    from backend.app.main import app

    routes = set(app.openapi()["paths"])
    assert path in routes
