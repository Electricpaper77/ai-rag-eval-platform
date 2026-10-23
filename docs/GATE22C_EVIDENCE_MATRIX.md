# Gate 22C evidence matrix

| Acceptance area | Evidence |
|---|---|
| Versioned lifecycle schema | `saas/migrations/003_lifecycle.sql`, migration ledger and Gate 21 disposable PostgreSQL job |
| Export schema/redaction | `saas/lifecycle.py::export_tenant`, `tests/test_gate22c_lifecycle.py`, `tests/test_gate22c_postgres_lifecycle.py` |
| RBAC and tenant isolation | Active owner/admin export checks and owner-only deletion checks in `saas/lifecycle.py`; disposable PostgreSQL test |
| Retention | Bounded 1–3650 day validation and dry-run counts in `cleanup_expired`; integration test |
| Transactional deletion/retry | Controlled failure rollback, anonymized tombstone, idempotent retry test |
| Audit evidence | `tenant_lifecycle_audit` rows for export/deletion requests and completion |
| Backup reintroduction | Gate 22B isolated `pg_dump`/`pg_restore` artifact; Gate 22C documents restore/re-delete reconciliation |
| Security boundary | Sessions, OIDC state, PKCE verifiers, bearer tokens, and Fernet keys excluded from exports |

The CI restore is disposable and does not prove managed backup retention, PITR, RPO/RTO, external-system deletion, or production authorization.
