import os
import pytest
from saas.postgres_repository import connect, create_run, require_membership, user_id

pytestmark = [pytest.mark.postgres_integration, pytest.mark.skipif(not os.getenv("AGENTTRUST_POSTGRES_URL"), reason="disposable PostgreSQL URL not configured")]

def test_postgres_schema_membership_and_quota_transaction():
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
