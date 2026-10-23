# SaaS threat model

- IDOR/cross-tenant reads and writes: every project, run, result, and evidence operation requires an active organization membership; `X-Organization-Id`, resource IDs, and idempotency keys are untrusted inputs. Add PostgreSQL row-level policy review before production.
- Unauthenticated access: all SaaS routes require configured bearer identity. The identity map is explicitly LOCAL/TEST ONLY, stores bearer secrets directly in configuration, and is rejected at runtime unless `AGENTTRUST_SAAS_RUNTIME_MODE` is explicitly `local` or `test`. Production requires managed OIDC, short-lived sessions, logout, and reset flows.
- Upload abuse: 2 MB body cap, 1–1000 JSON objects, strict JSONL parsing, and no filesystem paths.
- Retry double-run: organization-scoped idempotency uniqueness covers runs and usage events.
- Concurrent quota bypass: SQLite `BEGIN IMMEDIATE` serializes allocation in this local slice; production must use PostgreSQL transactions/locking and measured worker limits.
- Secret/payment risk: no password cryptography, raw cards, or live Stripe credentials are implemented or stored.
- Provider confusion: results say `provider=mock` and include an explicit limitation.
- Persistence boundary: SQLite transaction serialization is local-test correctness only; managed PostgreSQL, locking, backups, restore, and multi-instance validation remain blocked.
- OIDC boundary: production-mode identity accepts only a verified JWT from the configured issuer/audience and JWKS; internal identity is issuer+subject, never email. Authorization Code + PKCE state and nonce are single-use and five-minute bounded. Production session storage and provider-specific callback deployment remain required.
