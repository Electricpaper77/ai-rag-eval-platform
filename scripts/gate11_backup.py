"""Create and validate a portable checkpoint on the backup PVC."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import uuid

from backend.app.recovery.models import canonical_json, file_checksum, records_checksum, state_is_valid, utc_now
from backend.app.recovery.service import RecoveryService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-id", default=None)
    args = parser.parse_args()
    service = RecoveryService()
    document, valid = service.read_state()
    if not valid:
        service.mark_backup_failure()
        raise SystemExit("BACKUP_REJECTED_CHECKSUM_MISMATCH")
    backup_id = args.backup_id or f"backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    destination = service.backup_path / backup_id
    destination.mkdir(parents=True, exist_ok=False)
    state_file = destination / "state.json"
    state_file.write_text(canonical_json(document) + "\n", encoding="utf-8")
    config_file = None
    if service.config_path.exists():
        config_file = destination / "recovery-config.json"
        shutil.copy2(service.config_path, config_file)
    manifest = {
        "schema_version": 1,
        "backup_id": backup_id,
        "created_at": utc_now(),
        "record_count": len(document.get("records", [])),
        "latest_sequence": document.get("latest_sequence", 0),
        "state_checksum": document.get("checksum"),
        "state_file_sha256": file_checksum(state_file),
        "config_file_sha256": file_checksum(config_file) if config_file else None,
        "canonical_records_checksum": records_checksum(document.get("records", [])),
    }
    (destination / "manifest.json").write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    service.mark_backup(backup_id)
    print(f"BACKUP_CREATED backup_id={backup_id}")
    print(f"BACKUP_MANIFEST={destination / 'manifest.json'}")
    print(f"BACKUP_CHECKSUM={manifest['state_checksum']}")
    print(f"BACKUP_RECORDS={manifest['record_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
