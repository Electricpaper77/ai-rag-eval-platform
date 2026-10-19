"""Deterministic models and hashing helpers for recoverable AgentTrust state."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def canonical_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((dict(record) for record in records), key=lambda item: (int(item["sequence"]), str(item["id"])))


def records_checksum(records: Iterable[dict[str, Any]]) -> str:
    payload = canonical_json(canonical_records(records)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_state_document(records: Iterable[dict[str, Any]], generated_at: str | None = None) -> dict[str, Any]:
    normalized = canonical_records(records)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or utc_now(),
        "records": normalized,
        "latest_sequence": max((int(item["sequence"]) for item in normalized), default=0),
        "checksum": records_checksum(normalized),
    }


def state_is_valid(document: dict[str, Any]) -> bool:
    if document.get("schema_version") != SCHEMA_VERSION:
        return False
    records = document.get("records")
    if not isinstance(records, list):
        return False
    try:
        return document.get("checksum") == records_checksum(records) and document.get("latest_sequence", 0) == max(
            (int(item["sequence"]) for item in records), default=0
        )
    except (KeyError, TypeError, ValueError):
        return False


def file_checksum(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recovery_measurements(start_ns: int, end_ns: int, latest_before_failure: int, restored_sequence: int) -> dict[str, Any]:
    return {
        "rto_seconds": round(max(0, end_ns - start_ns) / 1_000_000_000, 6),
        "rpo_records_lost": max(0, int(latest_before_failure) - int(restored_sequence)),
    }
