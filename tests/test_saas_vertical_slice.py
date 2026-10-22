import json
import pytest
from saas.repository import create_org, create_project, create_run, get_run
from saas.router import identity

def test_customer_journey_and_tenant_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", str(tmp_path / "saas.sqlite3"))
    org_a=create_org("user-a","A"); org_b=create_org("user-b","B")
    project=create_project(org_a["id"],"user-a","Demo")
    run=create_run(org_a["id"],"user-a",project["id"],"run-1",[{"prompt":"hello"}],1000)
    assert run["provider"]=="mock" and get_run(org_a["id"],run["id"])["organization_id"]==org_a["id"]
    assert get_run(org_b["id"],run["id"]) is None

def test_saas_identity_requires_configured_bearer(monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_IDENTITIES",json.dumps({"a":{"user_id":"user-a"}}))
    assert identity("Bearer a")["user_id"]=="user-a"
    with pytest.raises(Exception): identity("Bearer unknown")
