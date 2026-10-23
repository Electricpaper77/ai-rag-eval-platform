"""Fail-closed SaaS deployment configuration checks."""
from __future__ import annotations

import json
import os
from cryptography.fernet import Fernet, InvalidToken


DEPLOYMENT_POLICIES = {"production", "staging"}


def validate_deployment_configuration() -> None:
    policy = os.getenv("AGENTTRUST_DEPLOYMENT_POLICY", "").strip().lower()
    runtime = os.getenv("AGENTTRUST_SAAS_RUNTIME_MODE", "").strip().lower()
    postgres = os.getenv("AGENTTRUST_POSTGRES_URL", "").strip()
    sqlite = os.getenv("AGENTTRUST_SAAS_DB", "").strip()
    identities = os.getenv("AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY", "{}").strip()
    oidc_configured = any(os.getenv(name, "").strip() for name in (
        "AGENTTRUST_OIDC_ISSUER", "AGENTTRUST_OIDC_CLIENT_ID",
        "AGENTTRUST_OIDC_REDIRECT_URI",
    ))

    if policy not in DEPLOYMENT_POLICIES:
        if oidc_configured and policy not in {"local", "test", "development"}:
            raise RuntimeError("explicit deployment policy required when OIDC is configured")
        return

    if os.getenv("AGENTTRUST_MANAGED_DEPLOYMENT", "").strip().lower() != "true":
        raise RuntimeError("managed deployment attestation is required")
    if runtime in {"local", "test"}:
        raise RuntimeError("local/test runtime is forbidden by deployment policy")
    if not postgres:
        raise RuntimeError("PostgreSQL is required by deployment policy")
    if sqlite:
        raise RuntimeError("SQLite is forbidden by deployment policy")
    if os.getenv("AGENTTRUST_SHARED_SESSION_STORE", "").strip().lower() != "postgres":
        raise RuntimeError("PostgreSQL shared session storage is required")
    encryption_key = os.getenv("AGENTTRUST_OIDC_STATE_ENCRYPTION_KEY", "").strip().encode()
    if not encryption_key:
        raise RuntimeError("OIDC state encryption key is required")
    try:
        Fernet(encryption_key)
    except (ValueError, TypeError, InvalidToken) as exc:
        raise RuntimeError("OIDC state encryption key is not a valid Fernet key") from exc
    if identities not in {"", "{}"}:
        try:
            configured = json.loads(identities)
        except json.JSONDecodeError as exc:
            raise RuntimeError("local/test identity configuration is invalid") from exc
        if configured:
            raise RuntimeError("local/test bearer identities are forbidden by deployment policy")
