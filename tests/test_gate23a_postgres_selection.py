import pytest

from saas.repository import selected_backend

def test_postgres_backend_is_explicit_and_fail_closed(monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_BACKEND", "postgres")
    monkeypatch.setenv("AGENTTRUST_POSTGRES_URL", "postgresql://synthetic.invalid/db")
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", "")
    assert selected_backend() == "postgres"

    monkeypatch.delenv("AGENTTRUST_POSTGRES_URL")
    with pytest.raises(RuntimeError, match="PostgreSQL backend selected"):
        selected_backend()

def test_sqlite_requires_explicit_local_path(monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_BACKEND", "sqlite")
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", "synthetic.sqlite3")
    assert selected_backend() == "sqlite"

def test_explicit_postgres_backend_selects_shared_session_store(monkeypatch):
    monkeypatch.setenv("AGENTTRUST_SAAS_BACKEND", "postgres")
    monkeypatch.setenv("AGENTTRUST_POSTGRES_URL", "postgresql://synthetic.invalid/db")
    monkeypatch.setenv("AGENTTRUST_SAAS_DB", "")
    monkeypatch.setenv("AGENTTRUST_DEPLOYMENT_POLICY", "test")
    from saas.router import session_store
    from saas.postgres_repository import PostgresSessionStore
    assert isinstance(session_store(), PostgresSessionStore)

