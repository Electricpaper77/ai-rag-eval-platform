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
from dataclasses import dataclass
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient


@dataclass(frozen=True)
class OIDCConfig:
    issuer: str
    audience: str
    authorization_endpoint: str
    jwks_uri: str
    client_id: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> "OIDCConfig":
        values = {k: os.getenv(k, "").strip() for k in (
            "AGENTTRUST_OIDC_ISSUER", "AGENTTRUST_OIDC_AUDIENCE",
            "AGENTTRUST_OIDC_AUTHORIZATION_ENDPOINT", "AGENTTRUST_OIDC_JWKS_URI",
            "AGENTTRUST_OIDC_CLIENT_ID", "AGENTTRUST_OIDC_REDIRECT_URI",
        )}
        if not all(values.values()):
            raise RuntimeError("OIDC configuration is incomplete")
        return cls(values["AGENTTRUST_OIDC_ISSUER"].rstrip("/"), values["AGENTTRUST_OIDC_AUDIENCE"], **{
            "authorization_endpoint": values["AGENTTRUST_OIDC_AUTHORIZATION_ENDPOINT"],
            "jwks_uri": values["AGENTTRUST_OIDC_JWKS_URI"],
            "client_id": values["AGENTTRUST_OIDC_CLIENT_ID"],
            "redirect_uri": values["AGENTTRUST_OIDC_REDIRECT_URI"],
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
