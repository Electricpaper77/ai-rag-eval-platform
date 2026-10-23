"""OIDC Authorization Code + PKCE primitives.

This module does not provide a local bearer fallback. Runtime configuration must
use a fixed issuer and audience; identity is keyed by issuer+subject, never email.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Protocol
from dataclasses import dataclass
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient
import httpx


@dataclass(frozen=True)
class OIDCConfig:
    issuer: str
    audience: str
    authorization_endpoint: str
    jwks_uri: str
    client_id: str
    redirect_uri: str
    token_endpoint: str = ""

    @classmethod
    def from_env(cls) -> "OIDCConfig":
        values = {k: os.getenv(k, "").strip() for k in (
            "AGENTTRUST_OIDC_ISSUER", "AGENTTRUST_OIDC_AUDIENCE",
            "AGENTTRUST_OIDC_AUTHORIZATION_ENDPOINT", "AGENTTRUST_OIDC_JWKS_URI",
            "AGENTTRUST_OIDC_CLIENT_ID", "AGENTTRUST_OIDC_REDIRECT_URI",
            "AGENTTRUST_OIDC_TOKEN_ENDPOINT",
        )}
        if not all(values.values()):
            raise RuntimeError("OIDC configuration is incomplete")
        return cls(values["AGENTTRUST_OIDC_ISSUER"].rstrip("/"), values["AGENTTRUST_OIDC_AUDIENCE"], **{
            "authorization_endpoint": values["AGENTTRUST_OIDC_AUTHORIZATION_ENDPOINT"],
            "jwks_uri": values["AGENTTRUST_OIDC_JWKS_URI"],
            "client_id": values["AGENTTRUST_OIDC_CLIENT_ID"],
            "redirect_uri": values["AGENTTRUST_OIDC_REDIRECT_URI"],
            "token_endpoint": values.get("AGENTTRUST_OIDC_TOKEN_ENDPOINT", ""),
        })


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def begin_login(config: OIDCConfig, state_store: dict[str, dict[str, object]], *, now: float | None = None) -> tuple[str, str]:
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    state_store[state] = {"nonce": nonce, "verifier": verifier, "expires_at": (now or time.time()) + 300}
    query = urlencode({"response_type": "code", "client_id": config.client_id, "redirect_uri": config.redirect_uri, "scope": "openid profile", "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"})
    return f"{config.authorization_endpoint}?{query}", state


def consume_login_state(state_store: dict[str, dict[str, object]], state: str, *, now: float | None = None) -> dict[str, object]:
    item = state_store.pop(state, None)
    if not item or float(item["expires_at"]) < (now or time.time()):
        raise ValueError("invalid or expired OIDC login state")
    return item


def verify_id_token(token: str, config: OIDCConfig, jwks: PyJWKClient | None = None, *, now: float | None = None, expected_nonce: str | None = None) -> dict[str, str]:
    client = jwks or PyJWKClient(config.jwks_uri)
    key = client.get_signing_key_from_jwt(token).key
    claims = jwt.decode(token, key=key, algorithms=["RS256", "RS384", "RS512"], audience=config.audience, issuer=config.issuer, options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]})
    if now is not None and int(claims["exp"]) <= now:
        raise jwt.ExpiredSignatureError("token expired")
    if expected_nonce is not None and claims.get("nonce") != expected_nonce:
        raise jwt.InvalidTokenError("OIDC nonce mismatch")
    return {"issuer": str(claims["iss"]), "subject": str(claims["sub"]), "email": str(claims.get("email", ""))}


def internal_user_key(claims: dict[str, str]) -> str:
    return f"{claims['issuer']}|{claims['subject']}"


class SessionStore(Protocol):
    def put(self, sid: str, user: dict[str, str], expires_at: float) -> None: ...
    def get(self, sid: str, now: float | None = None) -> dict[str, str] | None: ...
    def delete(self, sid: str) -> None: ...


class MemorySessionStore:
    """Deterministic test store; production must provide a shared encrypted store."""
    def __init__(self): self._items: dict[str, tuple[dict[str, str], float]] = {}
    def put(self, sid, user, expires_at): self._items[sid] = (dict(user), expires_at)
    def get(self, sid, now=None):
        item=self._items.get(sid)
        if not item or item[1] <= (time.time() if now is None else now): self._items.pop(sid, None); return None
        return dict(item[0])
    def delete(self, sid): self._items.pop(sid, None)


def exchange_code(config: OIDCConfig, code: str, verifier: str) -> str:
    if not config.token_endpoint: raise RuntimeError("OIDC token endpoint is not configured")
    response = httpx.post(config.token_endpoint, data={"grant_type":"authorization_code","code":code,"redirect_uri":config.redirect_uri,"client_id":config.client_id,"code_verifier":verifier}, timeout=10)
    response.raise_for_status(); token=response.json().get("id_token")
    if not token: raise ValueError("OIDC response did not contain id_token")
    return token
