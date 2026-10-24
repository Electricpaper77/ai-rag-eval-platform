"""Run bounded, synthetic recovery-maintenance operations.

This command is for disposable PostgreSQL/local artifacts only; it never selects
cloud storage or production databases.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from saas.operations import cleanup_backup_artifacts, recovery_measurement
from saas.postgres_repository import connect, migrate, user_id
from saas.lifecycle import DeletionJournal, delete_tenant, reconcile_restored_tenant, restore_access_allowed
from saas.recovery import RecoveryOrchestrator, write_approval
from scripts.secure_backup import create_backup, decrypt_for_restore


def _db_hash(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:16]


def run_end_to_end(args) -> int:
    if os.getenv("AGENTTRUST_DISPOSABLE_RECOVERY_AUTH", "").lower() != "true":
        raise SystemExit("AGENTTRUST_DISPOSABLE_RECOVERY_AUTH=true is required")
    if os.getenv("AGENTTRUST_DEPLOYMENT_POLICY", "").strip().lower() in {"production", "staging"}:
        raise SystemExit("end-to-end recovery drill is forbidden in deployment environments")
    source_url = os.getenv("AGENTTRUST_POSTGRES_URL", "").strip()
    if not source_url: raise SystemExit("AGENTTRUST_POSTGRES_URL is required")
    key = b"gate22e-disposable-backup-key-32"[:32]
    drill_id = uuid.uuid4().hex[:12]; work = args.evidence.parent / ("drill-" + drill_id); work.mkdir(parents=True, exist_ok=True)
    target = "restore_" + drill_id; values = conninfo_to_dict(source_url); admin = dict(values, dbname="postgres"); target_url = make_conninfo(**dict(values, dbname=target))
    started = time.monotonic_ns(); backup_started = time.monotonic_ns(); backup_at = datetime.now(timezone.utc)
    backup = work / "backup.enc"; manifest = work / "backup.enc.json"; plain = work / "restore.dump"; journal = DeletionJournal(work / "deletion-journal.jsonl")
    evidence = {"schema":"agenttrust-recovery-drill-v1", "drill_id":drill_id, "production_guarantee":False, "database_identities":{"source":_db_hash(values.get("dbname", "")),"target":_db_hash(target)}, "subprocesses":{"pg_dump":False,"pg_restore":False}, "outcome":"FAIL"}
    try:
        migrate()
        suffix = drill_id; org_a, org_b = "org_drill_a_" + suffix, "org_drill_b_" + suffix
        with connect() as conn:
            with conn.transaction():
                uid = user_id(conn, "https://issuer.example", "drill-operator")
                for org in (org_a, org_b):
                    project = "prj_" + org
                    conn.execute("INSERT INTO organizations(id,name,created_at) VALUES (%s,%s,now())", (org, org))
                    conn.execute("INSERT INTO memberships(organization_id,user_id,role,active,created_at) VALUES (%s,%s,'owner',TRUE,now())", (org, uid))
                    conn.execute("INSERT INTO projects(id,organization_id,name,created_at) VALUES (%s,%s,'Synthetic',now())", (project, org))
                    conn.execute("INSERT INTO evaluation_runs(id,organization_id,project_id,idempotency_key,status,provider,sample_count,created_at) VALUES (%s,%s,%s,%s,'completed','mock',1,now())", ("run_"+org,org,project,"idem_"+org))
                    conn.execute("INSERT INTO evaluation_results(run_id,organization_id,result_json,evidence_metadata_json,created_at) VALUES (%s,%s,'{}','{}',now())", ("run_"+org,org))
        create_backup(source_url, backup, key); evidence["subprocesses"]["pg_dump"] = True
        backup_finished = time.monotonic_ns(); event = journal.append(org_a, uid)
        with connect() as conn: delete_tenant(conn, org_a, uid, f"DELETE {org_a}")
        with psycopg.connect(make_conninfo(**admin), autocommit=True) as conn: conn.execute(f'CREATE DATABASE "{target}"')
        decrypt_for_restore(backup, manifest, key, plain)
        restore_started = time.monotonic_ns()
        subprocess.run(["pg_restore","--clean","--if-exists","--no-owner","--dbname",target_url,str(plain)], check=True, timeout=args.timeout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        evidence["subprocesses"]["pg_restore"] = True; restore_finished = time.monotonic_ns()
        with psycopg.connect(target_url) as conn:
            assert conn.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_a,)).fetchone()[0] == 1
            assert not restore_access_allowed(conn, org_a)
            reconcile_started = time.monotonic_ns(); reconcile_restored_tenant(conn, journal, org_a); reconcile_finished = time.monotonic_ns()
            assert not restore_access_allowed(conn, org_a)
            os.environ["AGENTTRUST_RECOVERY_APPROVAL_KEY"] = "gate22e-recovery-approval-key-32"[:32]; os.environ["AGENTTRUST_RECOVERY_APPROVERS"] = "drill-operator"
            approval = work / "approval.json"; write_approval(approval, "backup-drill", event["digest"], "drill-operator", target_database=target)
            promoted = RecoveryOrchestrator(conn, journal, approval, target).promote(org_a, "backup-drill", event["digest"])
            promotion_finished = time.monotonic_ns(); assert promoted["promoted"] and restore_access_allowed(conn, org_a)
            assert conn.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_a,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_b,)).fetchone()[0] == 1
        m = recovery_measurement(started/1e9, restore_finished/1e9, promotion_finished/1e9, backup_at.timestamp(), rto_objective_seconds=args.rto_objective, max_recovery_point_age_seconds=args.rpo_objective)
        m["observed"]["backup_seconds"] = (backup_finished-backup_started)/1e9; m["observed"]["promotion_seconds"] = (promotion_finished-reconcile_finished)/1e9
        m["observed"]["reconciliation_seconds"] = (reconcile_finished-reconcile_started)/1e9; m["observed"]["restore_seconds"] = (restore_finished-restore_started)/1e9
        evidence.update({"timestamps_utc":{"backup_created":backup_at.isoformat()},"measurement":m,"integrity":{"tenant_a_deleted":True,"tenant_b_intact":True,"quarantine_before_promotion":True,"authorized_promotion":True},"outcome":"PASS" if m["within_objectives"] else "FAIL"})
        if evidence["outcome"] != "PASS": raise RuntimeError("recovery objectives exceeded")
    except Exception as exc:
        evidence["failure"] = type(exc).__name__
        raise
    finally:
        args.evidence.parent.mkdir(parents=True, exist_ok=True); args.evidence.write_text(json.dumps(evidence, sort_keys=True) + "\n", encoding="utf-8");
        with psycopg.connect(make_conninfo(**admin), autocommit=True) as conn: conn.execute(f'DROP DATABASE IF EXISTS "{target}"')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--retention-seconds", type=int, default=86400)
    parser.add_argument("--execute", action="store_true", help="authorize deletion of expired disposable artifacts")
    parser.add_argument("--end-to-end", action="store_true")
    parser.add_argument("--evidence", type=Path, default=Path("artifacts/gate22e/recovery-drill.json"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--rto-objective", type=float, default=120.0)
    parser.add_argument("--rpo-objective", type=float, default=300.0)
    args = parser.parse_args()
    if args.end_to_end: return run_end_to_end(args)
    if os.getenv("AGENTTRUST_DEPLOYMENT_POLICY", "").strip().lower() in {"production", "staging"}:
        raise SystemExit("operational recovery drill cannot run against deployment environments")
    events = cleanup_backup_artifacts(args.backup_root, max_age_seconds=args.retention_seconds, execute=args.execute)
    print(json.dumps({"schema": "agenttrust-maintenance-v1", "dry_run": not args.execute,
                      "events": events, "secrets_included": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
