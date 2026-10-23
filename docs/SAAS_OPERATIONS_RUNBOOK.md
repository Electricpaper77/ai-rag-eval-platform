# SaaS PostgreSQL recovery runbook

Gate 22B validates this procedure only against disposable PostgreSQL databases. It never connects to production data.

1. Set `AGENTTRUST_POSTGRES_URL` to the isolated source database and run `python -c "from saas.postgres_repository import migrate; migrate()"`.
2. Create a custom-format backup with `pg_dump --format=custom --file agenttrust.dump "$AGENTTRUST_POSTGRES_URL"`. Keep the dump in protected managed storage; do not print the URL or credentials.
3. Create a new isolated restore database and run `pg_restore --clean --if-exists --no-owner --dbname "$RESTORE_URL" agenttrust.dump`.
4. Validate the migration ledger, tenant foreign keys, row counts, and authorization checks against the isolated restore. Do not overwrite the source database.
5. Preserve the dump, command exit codes, checksum, timestamps, and non-secret diagnostics as evidence.

The application migration runner creates `agenttrust_schema_migrations`, takes a transaction-scoped advisory lock, applies each numbered migration once, and rejects checksum drift or a missing/out-of-order ledger. A failed migration transaction rolls back. If a future migration cannot be made transactional, use a reviewed forward-recovery migration and record the exact failure and remediation before retrying.

Production blockers: managed backup retention, encryption/key management, restore authorization, point-in-time recovery, RPO/RTO evidence, alerting, and a scheduled recovery drill are not implemented here.
