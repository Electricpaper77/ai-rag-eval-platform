# SaaS threat model

- IDOR/cross-tenant reads: every project and run query includes organization scope; add PostgreSQL row-level policy review before production.
- Unauthenticated access: all SaaS routes require configured bearer identity. That identity map is explicitly LOCAL/TEST ONLY, stores bearer secrets directly in configuration, has no expiry/revocation, and must not be exposed as production authentication. Production requires managed OIDC, short-lived sessions, logout, and reset flows.
- Upload abuse: 2 MB body cap, 1–1000 JSON objects, strict JSONL parsing, and no filesystem paths.
- Retry double-run: organization-scoped idempotency uniqueness covers runs and usage events.
- Concurrent quota bypass: SQLite `BEGIN IMMEDIATE` serializes allocation in this local slice; production must use PostgreSQL transactions/locking and measured worker limits.
- Secret/payment risk: no password cryptography, raw cards, or live Stripe credentials are implemented or stored.
- Provider confusion: results say `provider=mock` and include an explicit limitation.
