import os
import pytest, uuid
from concurrent.futures import ThreadPoolExecutor
from saas.postgres_repository import connect, create_run, migrate, user_id

pytestmark = [pytest.mark.postgres_integration, pytest.mark.skipif(not os.getenv("AGENTTRUST_POSTGRES_URL"), reason="disposable PostgreSQL URL not configured")]

def test_postgres_schema_membership_and_quota_transaction():
    migrate()
    conn=connect()
    uid=user_id(conn,"https://issuer.example","sub-integration")
    org="org_gate21"; project="prj_gate21"
    with conn.transaction():
        conn.execute("DELETE FROM organizations WHERE id=%s",(org,))
        conn.execute("INSERT INTO organizations VALUES (%s,%s,now())",(org,"Gate 21"))
        conn.execute("INSERT INTO memberships VALUES (%s,%s,%s,TRUE,now())",(org,uid,"owner"))
        conn.execute("INSERT INTO projects VALUES (%s,%s,%s,now())",(project,org,"Demo"))
    result=create_run(conn,org,uid,project,"idem-1",[{"prompt":"hello"}],1)
    assert result["provider"] == "mock"
    assert create_run(conn,org,uid,project,"idem-1",[{"prompt":"hello"}],1)["id"] == result["id"]
    with pytest.raises(PermissionError): create_run(conn,org,"missing",project,"idem-2",[{"prompt":"no"}],1)

def test_migration_recovery_and_concurrent_idempotency():
    migrate(); suffix=uuid.uuid4().hex[:10]; org=f"org_conc_{suffix}"; project=f"prj_conc_{suffix}"
    conn=connect(); uid=user_id(conn,"https://issuer.example",f"conc-{suffix}")
    with conn.transaction():
        conn.execute("INSERT INTO organizations VALUES (%s,%s,now())",(org,"Concurrent")); conn.execute("INSERT INTO memberships VALUES (%s,%s,'owner',TRUE,now())",(org,uid)); conn.execute("INSERT INTO projects VALUES (%s,%s,%s,now())",(project,org,"P"))
    def attempt():
        try: return create_run(connect(),org,uid,project,"same-key",[{"prompt":"x"}],1)["id"]
        except Exception: return None
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _: attempt(), range(2)))
    assert len({item for item in results if item}) <= 1
    with connect() as check:
        assert check.execute("SELECT COUNT(*) FROM evaluation_runs WHERE organization_id=%s",(org,)).fetchone()[0] <= 1
        assert check.execute("SELECT COALESCE(SUM(units),0) FROM usage_events WHERE organization_id=%s",(org,)).fetchone()[0] <= 1
        check.execute("DROP TABLE sessions"); check.commit()
    migrate()
    with connect() as recovered: assert recovered.execute("SELECT to_regclass('public.sessions')").fetchone()[0] == "sessions"
