"""Verify a checkpoint before restoring it to the primary PVC."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import time

from backend.app.recovery.models import canonical_json, file_checksum, records_checksum, state_is_valid
from backend.app.recovery.service import RecoveryService


def _checkpoint_dir(root: Path, backup_id: str | None) -> Path:
    if (root / "manifest.json").exists():
        return root
    if backup_id:
        return root / backup_id
    candidates = sorted((path for path in root.glob("backup-*") if path.is_dir()), reverse=True)
    if not candidates:
        raise ValueError(f"no backup found under {root}")
    return candidates[0]


def verify_checkpoint(directory: Path) -> tuple[dict, dict]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    document = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    checks = {
        "state_file_sha256": file_checksum(directory / "state.json") == manifest.get("state_file_sha256"),
        "canonical_records_checksum": records_checksum(document.get("records", [])) == manifest.get("canonical_records_checksum"),
        "state_checksum": document.get("checksum") == manifest.get("state_checksum"),
        "document_valid": state_is_valid(document),
    }
    config_file = directory / "recovery-config.json"
    if manifest.get("config_file_sha256"):
        checks["config_file_sha256"] = config_file.exists() and file_checksum(config_file) == manifest["config_file_sha256"]
    if not all(checks.values()):
        raise ValueError("RESTORE_REJECTED_CHECKSUM_MISMATCH " + json.dumps(checks, sort_keys=True))
    return manifest, document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--backup-id", default=None)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--latest-pre-failure-sequence", type=int, default=None)
    args = parser.parse_args()
    service = RecoveryService()
    directory = _checkpoint_dir(args.backup_dir, args.backup_id)
    try:
        manifest, document = verify_checkpoint(directory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        service.mark_backup_failure()
        print(str(exc))
        return 2
    print(f"BACKUP_VERIFIED backup_id={manifest['backup_id']} checksum={manifest['state_checksum']}")
    if args.verify_only:
        return 0
    started = time.monotonic()
    latest_before_failure = args.latest_pre_failure_sequence or int(manifest.get("latest_sequence", 0))
    rpo_records_lost = max(0, latest_before_failure - int(manifest.get("latest_sequence", 0)))
    service.restore_document(document, duration_seconds=0.0, rpo_records_lost=rpo_records_lost)
    config_file = directory / "recovery-config.json"
    if config_file.exists():
        service.config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config_file, service.config_path)
    duration = round(time.monotonic() - started, 6)
    service._set_metadata(recovery_duration_seconds=duration, rpo_records_lost=rpo_records_lost)
    print(f"RESTORE_SUCCEEDED backup_id={manifest['backup_id']} records={manifest['record_count']} rpo_records_lost={rpo_records_lost} rto_seconds={duration}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
