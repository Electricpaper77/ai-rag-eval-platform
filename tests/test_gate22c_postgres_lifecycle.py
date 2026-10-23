import os, uuid, pytest
from saas.postgres_repository import connect, migrate, user_id
from saas.lifecycle import export_tenant, cleanup_expired, delete_tenant

pytestmark = pytest.mark.postgres_integration

def test_export_retention_delete_and_retry_are_tenant_scoped():
    if not os.getenv("AGENTTRUST_POSTGRES_URL"): pytest.fail("Gate 22C requires disposable PostgreSQL; refusing to skip")
    migrate(); suffix = uuid.uuid4().hex[:10]; org = f"org_lifecycle_{suffix}"; user = f"https://issuer/{suffix}"; uid = None
    with connect() as conn:
        with conn.transaction():
            uid = user_id(conn, user, "owner")
            conn.execute("INSERT INTO organizations(id,name,created_at) VALUES (%s,%s,now())", (org, "Lifecycle"))
            conn.execute("INSERT INTO memberships(organization_id,user_id,role,active,created_at) VALUES (%s,%s,'owner',TRUE,now())", (org, uid))
            conn.execute("INSERT INTO projects(id,organization_id,name,created_at) VALUES (%s,%s,'P',now())", (f"prj_{suffix}", org))
        exported = export_tenant(conn, org, uid)
        assert exported["schema"] == "agenttrust-tenant-export-v1"
        assert exported["manifest"]["record_counts"]["projects"] == 1
        assert "sessions" not in exported["records"]
        with pytest.raises(PermissionError): delete_tenant(conn, org, "missing", f"DELETE {org}")
        with pytest.raises(PermissionError): delete_tenant(conn, org, uid, "wrong")
        assert cleanup_expired(conn, dry_run=True)["dry_run"] is True
        with pytest.raises(RuntimeError): delete_tenant(conn, org, uid, f"DELETE {org}", fail_after="children")
        assert conn.execute("SELECT deleted_at FROM organizations WHERE id=%s", (org,)).fetchone()[0] is None
        assert delete_tenant(conn, org, uid, f"DELETE {org}")["deleted"] is True
        assert delete_tenant(conn, org, uid, f"DELETE {org}")["deleted"] is True
        assert conn.execute("SELECT COUNT(*) FROM tenant_lifecycle_audit WHERE organization_id=%s", (org,)).fetchone()[0] >= 3
import os, subprocess, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from saas.postgres_repository import connect, migrate, user_id
from saas.lifecycle import DeletionJournal, delete_tenant, reconcile_restored_tenant, restore_access_allowed

pytestmark = pytest.mark.postgres_integration

def _url_for_db(name):
    values = conninfo_to_dict(os.environ["AGENTTRUST_POSTGRES_URL"]); values["dbname"] = name
    return make_conninfo(**values)

def test_predeletion_backup_reappears_and_independent_journal_reconciles(tmp_path: Path):
    if not os.getenv("AGENTTRUST_POSTGRES_URL"): pytest.fail("Gate 22C requires disposable PostgreSQL; refusing to skip")
    migrate(); suffix = uuid.uuid4().hex[:8]; org_a, org_b = f"org_restore_a_{suffix}", f"org_restore_b_{suffix}"; dump = tmp_path / "predelete.dump"; journal = DeletionJournal(tmp_path / "deletions.jsonl")
    with connect() as conn:
        with conn.transaction():
            uid_a = user_id(conn, f"issuer/{suffix}", "a"); uid_b = user_id(conn, f"issuer/{suffix}", "b")
            for org, uid, name in ((org_a, uid_a, "Tenant A"), (org_b, uid_b, "Tenant B")):
                conn.execute("INSERT INTO organizations(id,name,created_at) VALUES (%s,%s,now())", (org, name)); conn.execute("INSERT INTO memberships(organization_id,user_id,role,active,created_at) VALUES (%s,%s,'owner',TRUE,now())", (org, uid)); conn.execute("INSERT INTO projects(id,organization_id,name,created_at) VALUES (%s,%s,'Project',now())", (f"prj_{org}", org)); conn.execute("INSERT INTO evaluation_runs(id,organization_id,project_id,idempotency_key,status,provider,sample_count,created_at) VALUES (%s,%s,%s,%s,'completed','mock',1,now())", (f"run_{org}", org, f"prj_{org}", f"idem_{org}")); conn.execute("INSERT INTO evaluation_results(run_id,organization_id,result_json,evidence_metadata_json,created_at) VALUES (%s,%s,'{}','{}',now())", (f"run_{org}", org)); conn.execute("INSERT INTO usage_events(id,organization_id,run_id,units,provider_cost_estimate_usd,idempotency_key,created_at) VALUES (%s,%s,%s,1,0,%s,now())", (f"use_{org}", org, f"run_{org}", f"idem_{org}"))
    subprocess.run(["pg_dump", "--format=custom", "--file", str(dump), os.environ["AGENTTRUST_POSTGRES_URL"]], check=True, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    journal.append(org_a, uid_a)
    with connect() as conn:
        assert delete_tenant(conn, org_a, uid_a, f"DELETE {org_a}")["deleted"]
        assert conn.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_a,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_b,)).fetchone()[0] == 1
    restore_name = f"restore_{suffix}"; admin = conninfo_to_dict(os.environ["AGENTTRUST_POSTGRES_URL"]); admin["dbname"] = "postgres"; admin_url = make_conninfo(**admin)
    with psycopg.connect(admin_url, autocommit=True) as admin_conn: admin_conn.execute(f'CREATE DATABASE "{restore_name}"')
    restore_url = _url_for_db(restore_name)
    try:
        subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--dbname", restore_url, str(dump)], check=True, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with psycopg.connect(restore_url) as restored:
            assert restored.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_a,)).fetchone()[0] == 1
            assert restored.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_b,)).fetchone()[0] == 1
            assert not restore_access_allowed(restored, org_a)
            assert reconcile_restored_tenant(restored, journal, org_a)["reconciled"]
            assert restore_access_allowed(restored, org_a)
            assert restored.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_a,)).fetchone()[0] == 0
            assert restored.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_b,)).fetchone()[0] == 1
            assert reconcile_restored_tenant(restored, journal, org_a)["already_reconciled"]
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin_conn: admin_conn.execute(f'DROP DATABASE IF EXISTS "{restore_name}"')

def test_concurrent_reconciliation_is_idempotent_and_fail_closed(tmp_path: Path):
    if not os.getenv("AGENTTRUST_POSTGRES_URL"): pytest.fail("Gate 22C requires disposable PostgreSQL; refusing to skip")
    migrate(); suffix = uuid.uuid4().hex[:8]; org_a, org_b = f"org_concurrent_a_{suffix}", f"org_concurrent_b_{suffix}"; journal = DeletionJournal(tmp_path / "deletions.jsonl"); uid = None
    with connect() as conn:
        with conn.transaction():
            uid = user_id(conn, f"issuer/{suffix}", "owner")
            for org in (org_a, org_b):
                conn.execute("INSERT INTO organizations(id,name,created_at) VALUES (%s,%s,now())", (org, org)); conn.execute("INSERT INTO memberships(organization_id,user_id,role,active,created_at) VALUES (%s,%s,'owner',TRUE,now())", (org, uid)); conn.execute("INSERT INTO projects(id,organization_id,name,created_at) VALUES (%s,%s,'P',now())", (f"prj_{org}", org))
    journal.append(org_a, uid)
    def worker():
        with connect() as conn: return reconcile_restored_tenant(conn, journal, org_a)
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: worker(), (1, 2)))
    assert sorted(item["already_reconciled"] for item in results) == [False, True]
    with connect() as conn:
        with pytest.raises(RuntimeError, match="no independent deletion evidence"): reconcile_restored_tenant(conn, journal, org_b)
        assert conn.execute("SELECT COUNT(*) FROM projects WHERE organization_id=%s", (org_b,)).fetchone()[0] == 1
