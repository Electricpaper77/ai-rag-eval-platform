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
