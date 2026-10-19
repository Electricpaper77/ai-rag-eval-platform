"""PVC-backed deterministic state service used by the Gate 11 workload."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge

from .models import build_state_document, canonical_json, records_checksum, state_is_valid, utc_now

BACKUP_SUCCESS = Counter("agenttrust_backup_success_total", "Successful state backups")
BACKUP_FAILURE = Counter("agenttrust_backup_failure_total", "Failed state backups")
RESTORE_SUCCESS = Counter("agenttrust_restore_success_total", "Successful state restores")
RESTORE_FAILURE = Counter("agenttrust_restore_failure_total", "Failed state restores")
LAST_BACKUP_TIMESTAMP = Gauge("agenttrust_last_successful_backup_timestamp", "Unix time of the last successful backup")
RECOVERY_DURATION = Gauge("agenttrust_recovery_duration_seconds", "Most recent recovery duration")
RPO_RECORDS_LOST = Gauge("agenttrust_rpo_records_lost", "Records not present in the restored checkpoint")
CHECKSUM_MISMATCH = Counter("agenttrust_state_checksum_mismatch_total", "Rejected state checksum validations")


def _env_path(name: str, default: str) -> Path:
    value = os.getenv(name, default).strip()
    return Path(value)


class RecoveryService:
    def __init__(self, primary_path: Path | None = None, backup_path: Path | None = None, config_path: Path | None = None):
        self.primary_path = primary_path or _env_path("RECOVERY_PRIMARY_PATH", "artifacts/recovery/state.json")
        self.backup_path = backup_path or _env_path("RECOVERY_BACKUP_PATH", "artifacts/recovery-backup")
        self.config_path = config_path or _env_path("RECOVERY_CONFIG_PATH", "config/recovery-config.json")
        self.metadata_path = self.primary_path.parent / "recovery-metadata.json"

    def _read_document(self) -> tuple[dict[str, Any], bool]:
        if not self.primary_path.exists():
            document = build_state_document([])
            return document, True
        try:
            document = json.loads(self.primary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}, False
        valid = state_is_valid(document)
        if not valid:
            CHECKSUM_MISMATCH.inc()
        return document, valid

    def _write_document(self, document: dict[str, Any]) -> dict[str, Any]:
        self.primary_path.parent.mkdir(parents=True, exist_ok=True)
        # The PVC is the synchronization boundary. Direct replacement also keeps
        # this path portable to Windows-based test runners where atomic rename of
        # files under the sandboxed temporary directory is not available.
        self.primary_path.write_text(canonical_json(document) + "\n", encoding="utf-8")
        return document

    def _metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return {}
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _set_metadata(self, **values: Any) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        current = self._metadata()
        current.update(values)
        self.metadata_path.write_text(canonical_json(current) + "\n", encoding="utf-8")

    def read_state(self) -> tuple[dict[str, Any], bool]:
        return self._read_document()

    def seed(self, count: int = 20, start: int = 1) -> dict[str, Any]:
        if count < 1 or count > 1000:
            raise ValueError("count must be between 1 and 1000")
        records = [
            {
                "id": f"recovery-{sequence:04d}",
                "sequence": sequence,
                "payload": {"model": "agenttrust-mock", "policy_version": "gate11-v1", "sequence": sequence},
            }
            for sequence in range(start, start + count)
        ]
        document = build_state_document(records)
        self._write_document(document)
        self._set_metadata(status="SEEDED", updated_at=utc_now())
        return document

    def append(self, count: int = 1) -> dict[str, Any]:
        document, valid = self._read_document()
        if not valid:
            raise ValueError("state checksum is invalid")
        start = int(document.get("latest_sequence", 0)) + 1
        existing = list(document.get("records", []))
        existing.extend(self.seed_records(count, start))
        updated = build_state_document(existing)
        self._write_document(updated)
        self._set_metadata(status="UPDATED", updated_at=utc_now())
        return updated

    @staticmethod
    def seed_records(count: int, start: int) -> list[dict[str, Any]]:
        return [
            {
                "id": f"recovery-{sequence:04d}",
                "sequence": sequence,
                "payload": {"model": "agenttrust-mock", "policy_version": "gate11-v1", "sequence": sequence},
            }
            for sequence in range(start, start + count)
        ]

    def corrupt(self) -> Path:
        self.primary_path.parent.mkdir(parents=True, exist_ok=True)
        self.primary_path.write_text(
            canonical_json({"schema_version": 1, "records": [{"id": "corrupt", "sequence": 999, "payload": {"corrupt": True}}], "latest_sequence": 999, "checksum": "invalid"}) + "\n",
            encoding="utf-8",
        )
        self._set_metadata(status="RECOVERY_REQUIRED", updated_at=utc_now())
        return self.primary_path

    def config_status(self) -> tuple[bool, dict[str, Any]]:
        if not self.config_path.exists():
            return False, {"reason": "config_missing", "path": str(self.config_path)}
        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False, {"reason": "config_invalid", "path": str(self.config_path)}
        required = {"model_name", "policy_version", "routing_mode"}
        if not required.issubset(config):
            return False, {"reason": "config_missing_keys", "path": str(self.config_path)}
        return True, config

    def status(self) -> dict[str, Any]:
        document, state_valid = self._read_document()
        config_valid, config = self.config_status()
        metadata = self._metadata()
        status = "HEALTHY" if state_valid and config_valid else "RECOVERY_REQUIRED"
        if state_valid and config_valid and metadata.get("status") == "RECOVERED":
            status = "RECOVERED"
        elif state_valid and config_valid and metadata.get("status") == "BACKED_UP":
            status = "BACKED_UP"
        return {
            "status": status,
            "schema_version": document.get("schema_version", 1),
            "record_count": len(document.get("records", [])) if isinstance(document.get("records", []), list) else 0,
            "latest_sequence": document.get("latest_sequence", 0),
            "checksum": document.get("checksum"),
            "state_checksum_valid": state_valid,
            "config_valid": config_valid,
            "config": config,
            "last_backup_at": metadata.get("last_backup_at"),
            "last_restore_at": metadata.get("last_restore_at"),
            "rpo_records_lost": metadata.get("rpo_records_lost", 0),
            "recovery_duration_seconds": metadata.get("recovery_duration_seconds"),
        }

    def checkpoint(self) -> dict[str, Any]:
        document, valid = self._read_document()
        if not valid:
            raise ValueError("cannot checkpoint invalid state")
        return {"status": "CHECKPOINT_READY", "checksum": records_checksum(document.get("records", [])), "record_count": len(document.get("records", []))}

    def mark_backup(self, backup_id: str) -> None:
        BACKUP_SUCCESS.inc()
        LAST_BACKUP_TIMESTAMP.set(datetime.now(timezone.utc).timestamp())
        self._set_metadata(status="BACKED_UP", backup_id=backup_id, last_backup_at=utc_now())

    def mark_backup_failure(self) -> None:
        BACKUP_FAILURE.inc()

    def restore_document(self, document: dict[str, Any], duration_seconds: float = 0.0, rpo_records_lost: int = 0) -> dict[str, Any]:
        if not state_is_valid(document):
            CHECKSUM_MISMATCH.inc()
            RESTORE_FAILURE.inc()
            raise ValueError("restore state checksum mismatch")
        self._write_document(document)
        RESTORE_SUCCESS.inc()
        RECOVERY_DURATION.set(duration_seconds)
        RPO_RECORDS_LOST.set(rpo_records_lost)
        self._set_metadata(status="RECOVERED", last_restore_at=utc_now(), recovery_duration_seconds=duration_seconds, rpo_records_lost=rpo_records_lost)
        return document


recovery_router = APIRouter(prefix="/platform/recovery", tags=["recovery"])
RECOVERY_SERVICE = RecoveryService()


def _service_error(exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=503)


@recovery_router.get("/status")
def recovery_status():
    result = RECOVERY_SERVICE.status()
    return JSONResponse(result, status_code=200 if result["state_checksum_valid"] and result["config_valid"] else 503)


@recovery_router.get("/state")
def recovery_state():
    document, valid = RECOVERY_SERVICE.read_state()
    if not valid:
        raise HTTPException(status_code=503, detail="state checksum mismatch")
    return document


@recovery_router.post("/checkpoint")
def recovery_checkpoint():
    try:
        return RECOVERY_SERVICE.checkpoint()
    except ValueError as exc:
        return _service_error(exc)


@recovery_router.post("/seed")
def recovery_seed(payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        return RECOVERY_SERVICE.seed(int(payload.get("count", 20)), int(payload.get("start", 1)))
    except (TypeError, ValueError) as exc:
        return _service_error(exc)


@recovery_router.post("/append")
def recovery_append(payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        return RECOVERY_SERVICE.append(int(payload.get("count", 1)))
    except (TypeError, ValueError) as exc:
        return _service_error(exc)
