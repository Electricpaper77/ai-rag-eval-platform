# SaaS launch checklist

- [ ] Configure and independently attest `AGENTTRUST_DEPLOYMENT_POLICY=staging|production`; startup must reject SQLite, process-local sessions, local/test identities, missing PostgreSQL, and missing shared-session configuration.
- [x] Replace process-local OIDC login state with shared expiring PostgreSQL storage and validate cross-instance callback routing in disposable CI.
- [ ] Complete production migration recovery, backup/restore, retention, deletion, and export controls.

- [ ] Managed OIDC with verified identities, short-lived sessions, logout, and reset.
- [ ] Production startup must reject `AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY`; only explicit isolated local/test mode may use it.
- [ ] Verify active-membership authorization for every organization, project, evaluation, result, and evidence read/write; treat organization headers as untrusted.
- [ ] Managed PostgreSQL migrations, backups, restore drill, retention, deletion, and export.
- [ ] Security review of every tenant query, role transition, rate limit, and quota path.
- [ ] Stripe sandbox contracts, signed webhook verification, replay protection, deduplication, and server-side entitlements.
- [ ] Production secrets/IAM, observability, incident runbooks, accessibility, and privacy review.
- [ ] Explicit approval before production deployment or real customer data.

Gate 20 is a tested foundation, not commercial launch approval.
