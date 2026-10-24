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

Gate 22E status: disposable recovery-drill maintenance, advisory-lock coordination,
dry-run backup cleanup, journal verification, and observed-only recovery timing
evidence are implemented. Production scheduling, cloud backup retention/PITR,
managed key custody, traffic switching, and RPO/RTO drills remain launch blockers.

Gate 22F status: provider-neutral key custody, synthetic key rotation/revocation,
separation-of-duties validation, retention catalog semantics, and sanitized alert
examples are tested locally. Managed KMS/HSM, immutable object storage, PITR,
external paging, production scheduling and operator separation remain blockers.

Gate 22F.1 status: deployment-style recovery promotion fails closed without
independently controlled requester/approver/role policy. The disposable provider
is not integrated with the encrypted backup path; catalog protection is local
simulation only and does not prove cloud WORM/object-lock.

Gate 23A status: a responsive synthetic/non-production workspace shell and
Playwright navigation test are implemented. Evaluation actions call the existing
authenticated API; no client-side authentication bypass or fabricated metrics are
used. Customer-facing hosting, managed identity, billing, and production launch
remain blocked.

Gate 23C status: evidence-backed evaluation policies, versioned decision history,
PASS/HOLD/INSUFFICIENT_EVIDENCE outcomes, authorized comparison, and JSON/CSV
exports are implemented with tenant authorization and recovery quarantine checks.
The mandatory integration path uses disposable PostgreSQL and Chromium with
synthetic metrics explicitly recorded by the test input. Production launch still
requires managed identity, persistence, backup/recovery operations, observability,
privacy review, and separate validation of any physical GPU/DCGM telemetry.

Gate 23D status: persisted case investigation, append-only reviewer annotations,
release-review snapshots, and tenant-scoped exports are implemented for synthetic
non-production validation. Missing per-case source data remains explicitly
`MISSING_EVIDENCE`; reviewer records do not authorize deployment. Managed reviewer
identity, production audit retention, external evidence storage, and operational
release governance remain blockers.

\n+Gate 23E UX evidence: PASS for authenticated synthetic onboarding, persisted
evaluation-to-release-review navigation, explicit missing-evidence states,
tenant-scoped error handling, keyboard focus, reduced-motion CSS, and 320/390/768/
1440px disposable Chromium screenshots. NOT production evidence: managed OIDC,
customer UI hosting, cloud audit retention, billing, production RPO/RTO, and
physical GPU/DCGM telemetry.

