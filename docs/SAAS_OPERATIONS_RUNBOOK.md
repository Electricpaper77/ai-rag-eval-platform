# SaaS PostgreSQL recovery runbook

Gate 22B validates this procedure only against disposable PostgreSQL databases. It never connects to production data.

1. Set `AGENTTRUST_POSTGRES_URL` to the isolated source database and run `python -c "from saas.postgres_repository import migrate; migrate()"`.
2. Create a custom-format backup with `pg_dump --format=custom --file agenttrust.dump "$AGENTTRUST_POSTGRES_URL"`. Keep the dump in protected managed storage; do not print the URL or credentials.
3. Create a new isolated restore database and run `pg_restore --clean --if-exists --no-owner --dbname "$RESTORE_URL" agenttrust.dump`.
4. Validate the migration ledger, tenant foreign keys, row counts, and authorization checks against the isolated restore. Do not overwrite the source database.
5. Preserve the dump, command exit codes, checksum, timestamps, and non-secret diagnostics as evidence.

The application migration runner creates `agenttrust_schema_migrations`, takes a transaction-scoped advisory lock, applies each numbered migration once, and rejects checksum drift or a missing/out-of-order ledger. A failed migration transaction rolls back. If a future migration cannot be made transactional, use a reviewed forward-recovery migration and record the exact failure and remediation before retrying.

Gate 22D adds `scripts/secure_backup.py` for authenticated encrypted disposable artifacts. Keep `AGENTTRUST_BACKUP_ENCRYPTION_KEY` in managed secret storage; manifests contain only a ciphertext digest and key id. Validate the manifest before decrypting, restore only into an isolated database, reconcile against an independently retained deletion journal, and require `saas.recovery.require_recovery_ready` before promotion. Missing, stale, mismatched or corrupt evidence leaves the restore quarantined.

Production blockers: managed backup retention, external key custody and rotation, point-in-time recovery, RPO/RTO evidence, alerting, scheduled cleanup/recovery drills, and an independently operated approval workflow remain unimplemented.

Gate 22E adds a bounded local maintenance command (`python scripts/recovery_drill.py --backup-root <dir>`). It is dry-run by default; `--execute` is required for disposable artifact deletion. CI measures observed restore/reconciliation timings only and does not establish production RPO/RTO. Production scheduling, cloud retention, managed key custody, traffic switching, and operator separation remain required.

Gate 22F adds a provider-neutral key-custody contract, disposable rotation/revocation tests, a retention catalog/object-lock simulation, low-cardinality Prometheus examples, and alert-rule validation. The local provider and catalog do not prove KMS/HSM custody, physical immutability, PITR, paging, or production scheduling.

