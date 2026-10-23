import json
import pytest
from saas.repository import create_org, create_project, create_run, get_run
from saas.router import identity

def test_customer_journey_and_tenant_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", str(tmp_path / "saas.sqlite3"))
    org_a=create_org("user-a","A"); org_b=create_org("user-b","B")
    project=create_project(org_a["id"],"user-a","Demo")
    run=create_run(org_a["id"],"user-a",project["id"],"run-1",[{"prompt":"hello"}],1000)
    assert run["provider"]=="mock" and get_run(org_a["id"],"user-a",run["id"])["organization_id"]==org_a["id"]
    with pytest.raises(PermissionError): create_project(org_a["id"],"user-b","cross-tenant")
    with pytest.raises(PermissionError): create_run(org_a["id"],"user-b",project["id"],"cross-tenant",[{"prompt":"no"}],1000)
    with pytest.raises(PermissionError): get_run(org_a["id"],"user-b",run["id"])
    assert get_run(org_b["id"],"user-b",run["id"]) is None

def test_saas_identity_requires_configured_bearer(monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_RUNTIME_MODE","test")
    monkeypatch.setenv("AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY",json.dumps({"a":{"user_id":"user-a"}}))
    assert identity("Bearer a")["user_id"]=="user-a"
    with pytest.raises(Exception): identity("Bearer unknown")

def test_saas_local_identity_fails_closed_in_production(monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_RUNTIME_MODE","production")
    monkeypatch.setenv("AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY",json.dumps({"a":{"user_id":"user-a"}}))
    with pytest.raises(Exception): identity("Bearer a")
