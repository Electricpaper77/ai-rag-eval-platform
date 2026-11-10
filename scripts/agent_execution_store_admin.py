"""Local, metadata-only operator commands for the SQLite tool outcome store.

Retention planning is read-only. This module does not schedule backups or
delete any files.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.app.tool_outcome_store import (  # noqa: E402
    SQLiteToolOutcomeStore,
    ToolOutcomeLockError,
    ToolOutcomeStoreError,
    ToolOutcomeSchemaError,
    ToolOutcomeSidecarError,
    validate_event_schema,
    validate_sqlite_sidecars,
)


BACKUP_NAME = re.compile(r"agent-exec-outcomes-(\d{8}T\d{6}Z)\.sqlite3\Z")
class OperatorCLIError(RuntimeError):
    """Safe reason-only error for operator output."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _existing_regular_file(path: Path) -> Path:
    if not path.is_absolute():
        raise OperatorCLIError("path_must_be_absolute")
    if path.is_symlink() or not path.is_file():
        raise OperatorCLIError("not_a_regular_file")
    return path.absolute()


def verify_database(
    path: Path | str, *, include_wal: bool = False
) -> dict[str, Any]:
    """Read-only integrity and schema check; return counts, never event data."""
    source = _existing_regular_file(Path(path))
    if os.name == "posix":
        if stat.S_IMODE(source.parent.stat().st_mode) & 0o077:
            raise OperatorCLIError("directory_permissions_unsafe")
        if stat.S_IMODE(source.stat().st_mode) & 0o077:
            raise OperatorCLIError("file_permissions_unsafe")
    try:
        validate_sqlite_sidecars(source)
    except ToolOutcomeSidecarError:
        raise OperatorCLIError("sidecar_path_unsafe") from None
    wal_path = Path(f"{source}-wal")
    if (not include_wal and wal_path.exists()
            and wal_path.stat().st_size > 0):
        raise OperatorCLIError("writer_must_be_stopped")
    # immutable prevents SQLite from creating WAL/SHM sidecars while checking
    # a quiesced database or standalone backup. The backup preflight opts into
    # ordinary read-only WAL handling to validate a live source snapshot.
    uri = f"{source.resolve().as_uri()}?mode=ro"
    if not include_wal:
        uri += "&immutable=1"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            check = connection.execute("PRAGMA integrity_check").fetchone()
            if check is None or check[0] != "ok":
                raise OperatorCLIError("integrity_failed")
            try:
                validate_event_schema(connection)
            except ToolOutcomeSchemaError:
                raise OperatorCLIError("schema_invalid") from None
            event_count = connection.execute(
                "SELECT count(*) FROM tool_outcome_events"
            ).fetchone()[0]
            unresolved_count = connection.execute("""
                SELECT count(*) FROM tool_outcome_events AS dispatch
                WHERE dispatch.event_type='dispatch'
                  AND NOT EXISTS (
                    SELECT 1 FROM tool_outcome_events AS terminal
                    WHERE terminal.run_id=dispatch.run_id
                      AND terminal.step_number=dispatch.step_number
                      AND terminal.event_type='terminal'
                  )
            """).fetchone()[0]
    except OperatorCLIError:
        raise
    except Exception:
        raise OperatorCLIError("database_unreadable") from None
    return {
        "path": str(source),
        "integrity": "ok",
        "event_count": int(event_count),
        "unresolved_dispatch_count": int(unresolved_count),
    }


def _parse_backup(path: Path) -> datetime | None:
    match = BACKUP_NAME.fullmatch(path.name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _iso_week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def plan_retention(directory: Path | str, now: datetime | None = None) -> dict[str, Any]:
    """Plan retention for verified, convention-named files without mutation.

    Keep the newest backup on each of the latest seven distinct UTC dates and
    the newest backup from each of the four most recently completed UTC ISO
    weeks. All other verified convention-named backups are expiration
    candidates. Unknown, future-dated, symlink, and invalid files are reported
    separately and are never expiration candidates.
    """
    root = Path(directory)
    if not root.is_absolute():
        raise OperatorCLIError("path_must_be_absolute")
    if root.is_symlink() or not root.is_dir():
        raise OperatorCLIError("backup_directory_invalid")
    if os.name == "posix" and stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise OperatorCLIError("directory_permissions_unsafe")
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise OperatorCLIError("retention_time_requires_timezone")
    instant = instant.astimezone(timezone.utc)

    verified: list[tuple[datetime, Path]] = []
    unclassified: list[str] = []
    unverified: list[dict[str, str]] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.is_symlink() or not path.is_file():
            unclassified.append(path.name)
            continue
        timestamp = _parse_backup(path)
        if timestamp is None or timestamp > instant:
            unclassified.append(path.name)
            continue
        try:
            verify_database(path)
        except OperatorCLIError as error:
            unverified.append({"name": path.name, "reason": error.reason})
            continue
        verified.append((timestamp, path))

    daily: dict[date, tuple[datetime, Path]] = {}
    for item in verified:
        timestamp, _ = item
        if timestamp.date() not in daily or timestamp > daily[timestamp.date()][0]:
            daily[timestamp.date()] = item
    keep: set[Path] = set()
    for day in sorted(daily, reverse=True)[:7]:
        keep.add(daily[day][1])

    current_week = _iso_week_start(instant.date())
    weekly: dict[date, tuple[datetime, Path]] = {}
    for item in verified:
        timestamp, path = item
        week_start = _iso_week_start(timestamp.date())
        if week_start >= current_week:
            continue
        if week_start not in weekly or timestamp > weekly[week_start][0]:
            weekly[week_start] = item
    prior_weeks = sorted(weekly, reverse=True)[:4]
    keep.update(weekly[week_start][1] for week_start in prior_weeks)

    expiration = sorted(
        (str(path) for _, path in verified if path not in keep)
    )
    retained = sorted(str(path) for path in keep)
    return {
        "operation": "retention-plan",
        "now_utc": instant.isoformat(),
        "policy": {
            "daily_distinct_utc_dates": 7,
            "completed_utc_iso_weeks": 4,
            "backup_name": "agent-exec-outcomes-YYYYMMDDTHHMMSSZ.sqlite3",
        },
        "retain": retained,
        "expiration_candidates": expiration,
        "unverified": unverified,
        "unclassified": unclassified,
        "deletion_performed": False,
        "schedule_created": False,
    }


def _event_fingerprint(path: Path) -> str:
    """Hash event rows internally for parity checks without exposing records."""
    digest = hashlib.sha256()
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        validate_sqlite_sidecars(path)
        with sqlite3.connect(uri, uri=True, timeout=5.0) as connection:
            cursor = connection.execute(
                "SELECT sequence, run_id, step_number, tool_name, event_type, "
                "status, reason_code, occurred_at FROM tool_outcome_events "
                "ORDER BY sequence"
            )
            while rows := cursor.fetchmany(256):
                for row in rows:
                    encoded = json.dumps(row, separators=(",", ":")).encode("utf-8")
                    digest.update(encoded)
                    digest.update(b"\n")
    except Exception:
        raise OperatorCLIError("event_comparison_failed") from None
    return digest.hexdigest()


def run_restore_drill(backup_path: Path | str) -> dict[str, Any]:
    """Restore into a private disposable directory and compare event records."""
    report: dict[str, Any] = {
        "operation": "restore-drill",
        "status": "FAIL",
        "event_count": None,
        "unresolved_dispatch_count": None,
        "records_match": False,
    }
    try:
        backup = _existing_regular_file(Path(backup_path))
        source_summary = verify_database(backup)
        source_fingerprint = _event_fingerprint(backup)
        with tempfile.TemporaryDirectory(prefix="agent-execution-restore-drill-") as tmp:
            workdir = Path(tmp)
            if os.name == "posix":
                os.chmod(workdir, 0o700)
            restored_path = workdir / "restored.sqlite3"
            restored = SQLiteToolOutcomeStore.restore_from(backup, restored_path)
            restored_summary = verify_database(restored.path)
            restored_fingerprint = _event_fingerprint(restored.path)
            records_match = (
                source_fingerprint == restored_fingerprint
                and source_summary["event_count"] == restored_summary["event_count"]
                and source_summary["unresolved_dispatch_count"]
                == restored_summary["unresolved_dispatch_count"]
            )
            report.update({
                "status": "PASS" if records_match else "FAIL",
                "event_count": restored_summary["event_count"],
                "unresolved_dispatch_count": restored_summary[
                    "unresolved_dispatch_count"
                ],
                "records_match": records_match,
            })
            if not records_match:
                report["reason"] = "records_mismatch"
    except OperatorCLIError as error:
        report["reason"] = error.reason
    except (ToolOutcomeStoreError, OSError, ValueError):
        report["reason"] = "restore_drill_failed"
    except Exception:
        report["reason"] = "restore_drill_failed"
    return report


def _preflight_recovery_database(path: Path | str) -> Path:
    """Validate a quiesced, safe database before recovery opens it for writing."""
    source = _existing_regular_file(Path(path))
    try:
        validate_sqlite_sidecars(source)
    except ToolOutcomeSidecarError:
        raise OperatorCLIError("sidecar_path_unsafe") from None
    if os.name == "posix":
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{source}{suffix}")
            try:
                sidecar_stat = sidecar.lstat()
            except FileNotFoundError:
                continue
            if stat.S_IMODE(sidecar_stat.st_mode) & 0o077:
                raise OperatorCLIError("sidecar_permissions_unsafe")
    # This performs immutable, read-only integrity/schema validation and
    # refuses a nonempty WAL before store construction can open the database.
    verify_database(source)
    return source


def run_recover_incomplete(database_path: Path | str,
                           *, executor_stopped_confirmed: bool) -> dict[str, Any]:
    """Recover unresolved dispatches after explicit local operator confirmation.

    The acknowledgement is not process-lock evidence. This command cannot
    prove that another executor or writer is stopped.
    """
    if not executor_stopped_confirmed:
        raise OperatorCLIError("executor_stop_not_confirmed")
    try:
        candidate = _existing_regular_file(Path(database_path)).resolve(strict=True)
        # Acquire the same nonblocking lock held by the executor around each
        # dispatch-to-terminal interval before inspecting mutable DB state.
        with SQLiteToolOutcomeStore.lock_for_path(candidate):
            source = _preflight_recovery_database(candidate)
            store = SQLiteToolOutcomeStore._from_locked_path(source)
            recovered = store._recover_incomplete_locked()
            # The store uses WAL mode. Leave a quiescent, standalone database
            # so a repeat can pass the nonempty-WAL preflight. This checkpoint
            # is post-commit and cannot roll back already-recorded outcomes.
            try:
                validate_sqlite_sidecars(source)
                with sqlite3.connect(source, timeout=5.0) as connection:
                    checkpoint = connection.execute(
                        "PRAGMA wal_checkpoint(TRUNCATE)"
                    ).fetchone()
                if checkpoint is None or checkpoint[0] != 0 or (
                    checkpoint[1] != -1 and checkpoint[1] != checkpoint[2]
                ):
                    raise OperatorCLIError("recovery_checkpoint_failed")
            except OperatorCLIError:
                raise
            except Exception:
                raise OperatorCLIError("recovery_checkpoint_failed") from None
    except ToolOutcomeLockError as error:
        if error.reason == "executor_active":
            raise OperatorCLIError("executor_active") from None
        raise OperatorCLIError(error.reason) from None
    return {
        "operation": "recover-incomplete",
        "status": "OK",
        "recovered_count": len(recovered),
    }


def _readiness_check(status: str, reason: str | None = None, **metadata: Any) -> dict[str, Any]:
    check: dict[str, Any] = {"status": status}
    if reason is not None:
        check["reason"] = reason
    check.update(metadata)
    return check


def _path_observation(path: Path) -> tuple[int, ...] | None:
    """Return metadata for a path without following links or reading contents."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return (
        info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode), info.st_size,
        info.st_mtime_ns, info.st_ctime_ns,
    )


def _directory_observation(path: Path) -> tuple[Any, ...] | None:
    metadata = _path_observation(path)
    if metadata is None:
        return None
    if metadata[2] != stat.S_IFDIR:
        return (metadata, None)
    entries = tuple(
        (entry.name, _path_observation(entry))
        for entry in sorted(path.iterdir(), key=lambda item: item.name)
    )
    return (metadata, entries)


def _readiness_observation(database: Path, backups: Path) -> dict[str, Any] | None:
    """Observe local identities/metadata only; this is not an atomic snapshot."""
    try:
        return {
            "database": _path_observation(database),
            "wal": _path_observation(Path(f"{database}-wal")),
            "shm": _path_observation(Path(f"{database}-shm")),
            "database_directory": _directory_observation(database.parent),
            "backup_directory": _directory_observation(backups),
        }
    except OSError:
        return None


def _storage_readiness_report(database_path: Path | str,
                              backup_directory: Path | str) -> dict[str, Any]:
    """Collect local checks before the consistency observation is applied.

    This function never creates paths or writes a report. Local PASS means
    only that the read-only checks below passed at the time they were sampled.
    Deployment readiness remains HOLD until an operator supplies and verifies
    target-specific controls.
    """
    database = Path(database_path)
    backups = Path(backup_directory)
    checks: dict[str, dict[str, Any]] = {}

    if not database.is_absolute():
        checks["database_exists"] = _readiness_check("FAIL", "path_must_be_absolute")
        checks["database_integrity_schema"] = _readiness_check("HOLD", "database_not_checked")
        checks["wal_shm_sidecars"] = _readiness_check("HOLD", "database_not_checked")
        checks["database_permissions"] = _readiness_check("HOLD", "database_not_checked")
    else:
        try:
            if database.is_symlink() or not database.is_file():
                raise OperatorCLIError("not_a_regular_file")
            checks["database_exists"] = _readiness_check("PASS")
        except OperatorCLIError as error:
            missing = (error.reason == "not_a_regular_file"
                       and not database.exists() and not database.is_symlink())
            status = "HOLD" if missing else "FAIL"
            checks["database_exists"] = _readiness_check(
                status, "database_missing" if missing else error.reason
            )

        try:
            if checks["database_exists"]["status"] != "PASS":
                checks["database_integrity_schema"] = _readiness_check("HOLD", "database_unavailable")
            else:
                details = verify_database(database)
                checks["database_integrity_schema"] = _readiness_check(
                    "PASS", integrity=details["integrity"],
                    event_count=details["event_count"],
                    unresolved_dispatch_count=details["unresolved_dispatch_count"],
                )
        except OperatorCLIError as error:
            status = "HOLD" if error.reason == "writer_must_be_stopped" else "FAIL"
            checks["database_integrity_schema"] = _readiness_check(status, error.reason)

        try:
            validate_sqlite_sidecars(database)
            sidecar_info: dict[str, str] = {}
            for suffix, label in (("-wal", "wal"), ("-shm", "shm")):
                sidecar = Path(f"{database}{suffix}")
                try:
                    sidecar_stat = sidecar.lstat()
                except FileNotFoundError:
                    sidecar_info[label] = "absent"
                    continue
                if not stat.S_ISREG(sidecar_stat.st_mode):
                    raise ToolOutcomeSidecarError("unsafe")
                sidecar_info[label] = "nonempty_regular" if sidecar_stat.st_size else "empty_regular"
            checks["wal_shm_sidecars"] = _readiness_check("PASS", **sidecar_info)
        except ToolOutcomeSidecarError:
            checks["wal_shm_sidecars"] = _readiness_check("FAIL", "sidecar_path_unsafe")

        if (checks["database_exists"]["status"] != "PASS"
                and checks["wal_shm_sidecars"]["status"] != "FAIL"):
            checks["wal_shm_sidecars"] = _readiness_check("HOLD", "database_unavailable")

        if os.name != "posix":
            checks["sqlite_sidecar_permissions"] = _readiness_check(
                "HOLD", "platform_acl_not_verified"
            )
        elif checks["database_exists"]["status"] != "PASS":
            checks["sqlite_sidecar_permissions"] = _readiness_check(
                "HOLD", "database_unavailable"
            )
        elif checks["wal_shm_sidecars"]["status"] != "PASS":
            checks["sqlite_sidecar_permissions"] = _readiness_check(
                "HOLD", "sidecar_path_unsafe"
            )
        else:
            try:
                unsafe = False
                for suffix in ("-wal", "-shm"):
                    try:
                        sidecar_stat = Path(f"{database}{suffix}").lstat()
                    except FileNotFoundError:
                        continue
                    if stat.S_IMODE(sidecar_stat.st_mode) & 0o077:
                        unsafe = True
                        break
                checks["sqlite_sidecar_permissions"] = _readiness_check(
                    "FAIL" if unsafe else "PASS",
                    "permissions_unsafe" if unsafe else None,
                )
            except OSError:
                checks["sqlite_sidecar_permissions"] = _readiness_check(
                    "FAIL", "permissions_unreadable"
                )

        if os.name != "posix":
            checks["database_permissions"] = _readiness_check("HOLD", "platform_acl_not_verified")
        elif checks["database_exists"]["status"] != "PASS":
            checks["database_permissions"] = _readiness_check("HOLD", "database_unavailable")
        else:
            try:
                db_stat = database.lstat()
                parent_stat = database.parent.stat()
                if (not stat.S_ISREG(db_stat.st_mode)
                        or stat.S_IMODE(db_stat.st_mode) & 0o077
                        or stat.S_IMODE(parent_stat.st_mode) & 0o077):
                    checks["database_permissions"] = _readiness_check("FAIL", "permissions_unsafe")
                else:
                    checks["database_permissions"] = _readiness_check("PASS")
            except OSError:
                checks["database_permissions"] = _readiness_check("FAIL", "permissions_unreadable")

    if not backups.is_absolute():
        checks["backup_directory"] = _readiness_check("FAIL", "path_must_be_absolute")
        checks["retention_plan"] = _readiness_check("HOLD", "backup_directory_unavailable")
    elif backups.is_symlink() or not backups.is_dir():
        missing = not backups.exists() and not backups.is_symlink()
        checks["backup_directory"] = _readiness_check(
            "HOLD" if missing else "FAIL",
            "backup_directory_missing" if missing else "backup_directory_invalid",
        )
        checks["retention_plan"] = _readiness_check("HOLD", "backup_directory_unavailable")
    elif os.name == "posix" and stat.S_IMODE(backups.stat().st_mode) & 0o077:
        checks["backup_directory"] = _readiness_check("FAIL", "permissions_unsafe")
        checks["retention_plan"] = _readiness_check("HOLD", "backup_directory_unsafe")
    else:
        checks["backup_directory"] = _readiness_check(
            "PASS" if os.name == "posix" else "HOLD",
            None if os.name == "posix" else "platform_acl_not_verified",
        )
        try:
            plan = plan_retention(backups)
            checks["retention_plan"] = _readiness_check(
                "FAIL" if plan["unverified"] else "PASS",
                "unverified_backups" if plan["unverified"] else None,
                retained_count=len(plan["retain"]),
                expiration_candidate_count=len(plan["expiration_candidates"]),
                unverified_count=len(plan["unverified"]),
                unclassified_count=len(plan["unclassified"]),
                deletion_performed=False, schedule_created=False,
            )
        except OperatorCLIError as error:
            checks["retention_plan"] = _readiness_check("FAIL", error.reason)

    target_evidence = {
        "deployment_target_identified": "HOLD",
        "service_and_recovery_identities_verified": "HOLD",
        "target_acl_evidence": "HOLD",
        "retention_scheduler_verified": "HOLD",
        "target_restore_drill_verified": "HOLD",
    }
    local_statuses = [check["status"] for check in checks.values()]
    local_status = "FAIL" if "FAIL" in local_statuses else (
        "HOLD" if "HOLD" in local_statuses else "PASS"
    )
    return {
        "operation": "readiness",
        "status": "FAIL" if local_status == "FAIL" else "HOLD",
        "local_status": local_status,
        "deployment_status": "HOLD",
        "checks": checks,
        "deployment_evidence": target_evidence,
    }


def storage_readiness(database_path: Path | str,
                      backup_directory: Path | str) -> dict[str, Any]:
    """Report local readiness, holding if observed storage changes mid-check."""
    database = Path(database_path)
    backups = Path(backup_directory)
    before = _readiness_observation(database, backups)
    report = _storage_readiness_report(database, backups)
    after = _readiness_observation(database, backups)
    checks = report["checks"]

    if before is None or after is None:
        consistency = _readiness_check("HOLD", "storage_observation_unavailable")
    elif before != after:
        consistency = _readiness_check("HOLD", "storage_changed_during_check")
        if before.get("database") != after.get("database") or any(
            before.get(key) != after.get(key) for key in ("wal", "shm")
        ):
            if checks["database_integrity_schema"]["status"] != "FAIL":
                checks["database_integrity_schema"] = _readiness_check(
                    "HOLD", "storage_changed_during_check"
                )
            final_database = after.get("database")
            if final_database is None:
                if checks["database_exists"]["status"] != "FAIL":
                    checks["database_exists"] = _readiness_check(
                        "HOLD", "storage_changed_during_check"
                    )
            elif final_database[2] != stat.S_IFREG:
                checks["database_exists"] = _readiness_check(
                    "FAIL", "database_path_unsafe"
                )
            final_sidecars = (after.get("wal"), after.get("shm"))
            if any(item is not None and item[2] != stat.S_IFREG for item in final_sidecars):
                checks["wal_shm_sidecars"] = _readiness_check(
                    "FAIL", "sidecar_path_unsafe"
                )
            elif checks["wal_shm_sidecars"]["status"] != "FAIL":
                checks["wal_shm_sidecars"] = _readiness_check(
                    "HOLD", "storage_changed_during_check"
                )
        if before.get("backup_directory") != after.get("backup_directory"):
            if checks["retention_plan"]["status"] != "FAIL":
                checks["retention_plan"] = _readiness_check(
                    "HOLD", "storage_changed_during_check"
                )
            final_backup_dir = after.get("backup_directory")
            if final_backup_dir is None:
                if checks["backup_directory"]["status"] != "FAIL":
                    checks["backup_directory"] = _readiness_check(
                        "HOLD", "storage_changed_during_check"
                    )
            elif final_backup_dir[0][2] != stat.S_IFDIR:
                checks["backup_directory"] = _readiness_check(
                    "FAIL", "backup_directory_invalid"
                )
    else:
        consistency = _readiness_check("PASS")

    checks["storage_consistency"] = consistency
    statuses = [check["status"] for check in checks.values()]
    report["local_status"] = "FAIL" if "FAIL" in statuses else (
        "HOLD" if "HOLD" in statuses else "PASS"
    )
    report["status"] = "FAIL" if report["local_status"] == "FAIL" else "HOLD"
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local metadata-only backup and recovery tools for Agent Execution."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    backup = commands.add_parser("backup", help="create a new verified SQLite backup")
    backup.add_argument("--database", type=Path, required=True)
    backup.add_argument("--destination", type=Path, required=True)

    verify = commands.add_parser("verify", help="read-only integrity/schema check")
    verify.add_argument("--database", type=Path, required=True)

    restore = commands.add_parser("restore", help="restore to a new database path")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)

    drill = commands.add_parser(
        "restore-drill", help="restore a backup temporarily and compare event records"
    )
    drill.add_argument("--backup", type=Path, required=True)

    retention = commands.add_parser(
        "retention-plan", help="list retention decisions without deleting files"
    )
    retention.add_argument("--directory", type=Path, required=True)
    retention.add_argument(
        "--now", help="timezone-aware ISO timestamp for deterministic planning"
    )
    readiness = commands.add_parser(
        "readiness", help="read-only local storage checks and deployment evidence gaps"
    )
    readiness.add_argument("--database", type=Path, required=True)
    readiness.add_argument("--backup-directory", type=Path, required=True)
    recover = commands.add_parser(
        "recover-incomplete",
        help="mark unresolved dispatches unknown after operator confirmation",
    )
    recover.add_argument("--database", type=Path, required=True)
    recover.add_argument("--confirm-executor-stopped", action="store_true")
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "readiness":
        return storage_readiness(args.database, args.backup_directory)
    if args.command == "recover-incomplete":
        return run_recover_incomplete(
            args.database,
            executor_stopped_confirmed=args.confirm_executor_stopped,
        )
    if args.command == "verify":
        return {"operation": "verify", **verify_database(args.database)}

    if args.command == "backup":
        source_path = _existing_regular_file(args.database)
        if not args.destination.is_absolute():
            raise OperatorCLIError("path_must_be_absolute")
        name_timestamp = _parse_backup(args.destination)
        if name_timestamp is None:
            raise OperatorCLIError("backup_name_invalid")
        if name_timestamp > datetime.now(timezone.utc):
            raise OperatorCLIError("backup_name_invalid")
        if args.destination.exists() or args.destination.is_symlink():
            raise OperatorCLIError("destination_exists")
        # The online backup API can take a consistent snapshot including WAL
        # state. The source's immutable schema check is only a preflight.
        verify_database(source_path, include_wal=True)
        store = SQLiteToolOutcomeStore(source_path)
        created = store.backup_to(args.destination)
        details = verify_database(created)
        return {"operation": "backup", **details}

    if args.command == "restore":
        backup = _existing_regular_file(args.backup)
        if not args.destination.is_absolute():
            raise OperatorCLIError("path_must_be_absolute")
        verify_database(backup)
        if args.destination.exists() or args.destination.is_symlink():
            raise OperatorCLIError("destination_exists")
        restored = SQLiteToolOutcomeStore.restore_from(backup, args.destination)
        return {"operation": "restore", **verify_database(restored.path)}

    if args.command == "restore-drill":
        return run_restore_drill(args.backup)

    instant = None
    if args.now is not None:
        try:
            instant = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        except ValueError:
            raise OperatorCLIError("retention_time_invalid") from None
    return plan_retention(args.directory, instant)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = _run(args)
    except (OperatorCLIError, ToolOutcomeStoreError, OSError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "operation": args.command,
                          "reason": getattr(error, "reason", "operation_failed")},
                         sort_keys=True))
        return 2
    result.setdefault("status", "OK")
    print(json.dumps(result, sort_keys=True))
    if result["status"] == "FAIL":
        return 2
    if args.command == "readiness" and result["status"] == "HOLD":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
