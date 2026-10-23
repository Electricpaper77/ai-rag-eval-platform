import os
import pytest, uuid
from concurrent.futures import ThreadPoolExecutor, wait
import psycopg
from saas.postgres_repository import connect, create_run, migrate, user_id

pytestmark = [pytest.mark.postgres_integration, pytest.mark.skipif(not os.getenv("AGENTTRUST_POSTGRES_URL"), reason="disposable PostgreSQL URL not configured")]

def _blocking_diagnostics():
    with connect() as conn:
        return conn.execute("""
            SELECT pid, state, wait_event_type, wait_event,
                   pg_blocking_pids(pid)
            FROM pg_stat_activity
            WHERE datname = current_database()
            ORDER BY pid
        """).fetchall()

def _assert_finished(futures, label):
    done, _ = wait(futures, timeout=20)
    if len(done) != len(futures):
        pytest.fail(f"{label} timed out; pg_stat_activity={_blocking_diagnostics()}")

def test_postgres_schema_membership_and_quota_transaction():
    migrate()
    org="org_gate21"; project="prj_gate21"
    with connect() as conn:
        with conn.transaction():
            uid=user_id(conn,"https://issuer.example","sub-integration")
            conn.execute("DELETE FROM organizations WHERE id=%s",(org,))
            conn.execute("INSERT INTO organizations VALUES (%s,%s,now())",(org,"Gate 21"))
            conn.execute("INSERT INTO memberships VALUES (%s,%s,%s,TRUE,now())",(org,uid,"owner"))
            conn.execute("INSERT INTO projects VALUES (%s,%s,%s,now())",(project,org,"Demo"))
    with connect() as visible:
        assert visible.execute("SELECT COUNT(*) FROM projects WHERE id=%s AND organization_id=%s",(project,org)).fetchone()[0] == 1
    with connect() as conn:
        result=create_run(conn,org,uid,project,"idem-1",[{"prompt":"hello"}],1)
        assert result["provider"] == "mock"
        assert create_run(conn,org,uid,project,"idem-1",[{"prompt":"hello"}],1)["id"] == result["id"]
        with pytest.raises(PermissionError): create_run(conn,org,"missing",project,"idem-2",[{"prompt":"no"}],1)

def test_migration_recovery_and_concurrent_idempotency():
    migrate(); suffix=uuid.uuid4().hex[:10]; org=f"org_conc_{suffix}"; project=f"prj_conc_{suffix}"
    with connect() as conn:
        with conn.transaction():
            uid=user_id(conn,"https://issuer.example",f"conc-{suffix}")
            conn.execute("INSERT INTO organizations VALUES (%s,%s,now())",(org,"Concurrent")); conn.execute("INSERT INTO memberships VALUES (%s,%s,'owner',TRUE,now())",(org,uid)); conn.execute("INSERT INTO projects VALUES (%s,%s,%s,now())",(project,org,"P"))
    with connect() as visible:
        assert visible.execute("SELECT COUNT(*) FROM memberships WHERE organization_id=%s AND user_id=%s",(org,uid)).fetchone()[0] == 1

    def attempt(org_id, project_id, key, barrier):
        barrier.wait(timeout=10)
        with connect() as worker:
            try:
                return ("ok", create_run(worker,org_id,uid,project_id,key,[{"prompt":"x"}],1))
            except PermissionError as exc:
                return ("quota_rejected", str(exc))
            except psycopg.errors.UniqueViolation as exc:
                return ("unique_violation", str(exc))

    barrier = __import__("threading").Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(attempt,org,project,"same-key",barrier) for _ in range(2)]
        _assert_finished(futures, "concurrent idempotency workers")
        same_results=[future.result(timeout=1) for future in futures]
    assert all(kind == "ok" for kind,_ in same_results), same_results
    same_ids={payload["id"] for _,payload in same_results}
    assert len(same_ids) == 1, same_results

    org2=f"org_quota_{suffix}"; project2=f"prj_quota_{suffix}"
    with connect() as conn:
        with conn.transaction():
            conn.execute("INSERT INTO organizations VALUES (%s,%s,now())",(org2,"Quota")); conn.execute("INSERT INTO memberships VALUES (%s,%s,'owner',TRUE,now())",(org2,uid)); conn.execute("INSERT INTO projects VALUES (%s,%s,%s,now())",(project2,org2,"Q"))
    barrier = __import__("threading").Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(attempt,org2,project2,key,barrier) for key in ("distinct-a","distinct-b")]
        _assert_finished(futures, "quota workers")
        distinct_results=[future.result(timeout=1) for future in futures]
    assert sorted(kind for kind,_ in distinct_results) == ["ok","quota_rejected"], distinct_results
    with connect() as check:
        assert check.execute("SELECT COUNT(*) FROM evaluation_runs WHERE organization_id=%s",(org,)).fetchone()[0] == 1
        assert check.execute("SELECT COALESCE(SUM(units),0) FROM usage_events WHERE organization_id=%s",(org,)).fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM evaluation_runs WHERE organization_id=%s",(org2,)).fetchone()[0] == 1
        assert check.execute("SELECT COALESCE(SUM(units),0) FROM usage_events WHERE organization_id=%s",(org2,)).fetchone()[0] == 1
        # Recovery is isolated to a disposable, uniquely named table; shared
        # application schema is never dropped during concurrency validation.
        scratch=f"gate21_partial_{suffix}"
        check.execute(f'CREATE TABLE "{scratch}" (id integer)')
        check.commit()
        with pytest.raises(psycopg.Error):
            with check.transaction():
                check.execute(f'INSERT INTO "{scratch}" VALUES (1)')
                check.execute(f'INSERT INTO "{scratch}" (missing_column) VALUES (2)')
        check.execute(f'DROP TABLE "{scratch}"'); check.commit()
    migrate()
    with connect() as recovered: assert recovered.execute("SELECT to_regclass('public.sessions')").fetchone()[0] == "sessions"
