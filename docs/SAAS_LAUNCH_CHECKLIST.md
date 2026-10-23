# SaaS launch checklist

- [ ] Configure and independently attest `AGENTTRUST_DEPLOYMENT_POLICY=staging|production`; startup must reject SQLite, process-local sessions, local/test identities, missing PostgreSQL, and missing shared-session configuration.
- [x] Replace process-local OIDC login state with shared expiring PostgreSQL storage and validate cross-instance callback routing in disposable CI.
- [ ] Complete production migration recovery, backup/restore, retention, deletion, and export controls. Gate 22B validates an isolated disposable-PostgreSQL dump/restore only; it does not exercise production data or managed backup retention.
- [x] Gate 22C defines tenant export/deletion authorization, transactional tombstones, bounded retention dry-run, redaction, and disposable PostgreSQL tests. Scheduled execution and backup reconciliation remain blocked.

- [ ] Managed OIDC with verified identities, short-lived sessions, logout, and reset.
- [ ] Production startup must reject `AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY`; only explicit isolated local/test mode may use it.
- [ ] Verify active-membership authorization for every organization, project, evaluation, result, and evidence read/write; treat organization headers as untrusted.
- [ ] Managed PostgreSQL migrations, backups, restore drill, retention, deletion, and export. Versioned migration checksums and advisory-lock serialization are validated locally/CI; managed operational recovery remains blocked.
- [ ] Security review of every tenant query, role transition, rate limit, and quota path.
- [ ] Stripe sandbox contracts, signed webhook verification, replay protection, deduplication, and server-side entitlements.
- [ ] Production secrets/IAM, observability, incident runbooks, accessibility, and privacy review.
- [ ] Explicit approval before production deployment or real customer data.

Gate 22D status: versioned OIDC state key handling, encrypted backup integrity,
restore quarantine/approval helpers, and the recovery-promotion ledger are
implemented and tested against disposable/local fixtures. Managed secret
custody, scheduled operations, independent approval, PITR, backup retention,
and measured recovery drills remain launch blockers.

Gate 20 is a tested foundation, not commercial launch approval.
