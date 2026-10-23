# SaaS threat model

- IDOR/cross-tenant reads and writes: every project, run, result, and evidence operation requires an active organization membership; `X-Organization-Id`, resource IDs, and idempotency keys are untrusted inputs. Add PostgreSQL row-level policy review before production.
- Unauthenticated access: all SaaS routes require configured bearer identity. The identity map is explicitly LOCAL/TEST ONLY, stores bearer secrets directly in configuration, and is rejected by the independently controlled `AGENTTRUST_DEPLOYMENT_POLICY` boundary for staging/production. Those policies also require managed-deployment attestation, PostgreSQL, and shared PostgreSQL sessions; missing controls fail startup.
- Upload abuse: 2 MB body cap, 1–1000 JSON objects, strict JSONL parsing, and no filesystem paths.
- Retry double-run: organization-scoped idempotency uniqueness covers runs and usage events.
- Concurrent quota bypass: SQLite `BEGIN IMMEDIATE` serializes allocation in this local slice; production must use PostgreSQL transactions/locking and measured worker limits.
- Secret/payment risk: no password cryptography, raw cards, or live Stripe credentials are implemented or stored.
- Provider confusion: results say `provider=mock` and include an explicit limitation.
- Persistence boundary: SQLite and `MemorySessionStore` are isolated development/test facilities. Managed PostgreSQL, backups, restore, retention/deletion/export, and operational multi-instance validation remain blocked. The current login state map is process-local; shared state is still a production-launch blocker.
- OIDC boundary: production-mode identity accepts only a verified JWT from the configured issuer/audience and JWKS; internal identity is issuer+subject, never email. Authorization Code + PKCE state and nonce are single-use and five-minute bounded. Production session storage and provider-specific callback deployment remain required.
