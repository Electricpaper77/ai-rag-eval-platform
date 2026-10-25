# AgentTrust IQ SaaS architecture

Production shape: external OIDC identity → FastAPI authorization → managed PostgreSQL → bounded evaluation execution → tenant-scoped JSON/JSONL evidence. The local slice keeps the existing FastAPI process and uses SQLite only for reproducible tests. Its configured bearer identity map is LOCAL/TEST ONLY and is not production authentication. No Kubernetes, microservice, Redis, or broker is justified by current measured requirements.

Gate 22A adds PostgreSQL-backed, expiring OIDC login state with hashed state identifiers, encrypted PKCE/nonce payloads, issuer/client/redirect binding, atomic one-time consumption, and cleanup. Gate 22B adds a versioned migration ledger with SHA-256 checksums and transaction-scoped advisory-lock serialization, plus an isolated `pg_dump`/`pg_restore` drill. These are disposable-environment controls; managed backup retention, restore runbooks, and production migration recovery remain blocked. The deployment policy independently rejects staging/production startup without managed attestation, PostgreSQL, shared PostgreSQL sessions, and a valid Fernet state key, and rejects local identities and SQLite. No provider, billing, deployment, or customer authentication rollout is claimed.
Versioned key rotation, managed secret-provider integration, and scheduled cleanup remain production blockers. `saas/migrations/002_postgres.sql` and `saas/postgres_repository.py` provide the PostgreSQL foundation with active-membership checks, unique idempotency, and per-organization advisory locking for quota allocation.

Entities are organizations, memberships, projects, evaluation_runs, evaluation_results, usage_events, and audit_events. `saas/migrations/001_initial.sql` is an additive migration; production requires reviewed down migration, backups, and restore testing. Cost drivers are estimates only: managed database, API compute, evidence storage, identity MAU, and model-provider usage. No paid infrastructure was deployed.

Gate 23C adds `evaluation_policies` and `evaluation_decisions` as versioned,
tenant-scoped records. The decision engine reads only explicit `quality_metrics`
stored with persisted runs, records the policy version and evidence references,
and uses PostgreSQL advisory locking plus uniqueness constraints for idempotent
decision creation. The browser scorecard is a view over authenticated API data;
it does not create identities or invent evaluation results. Disposable PostgreSQL
and Chromium validate the path; managed production operations remain unverified.

Gate 23D adds tenant-scoped persisted case evidence, append-only reviewer
annotation revisions, and release-review snapshots. The API distinguishes real
stored case evidence from `MISSING_EVIDENCE`, derives reviewer identity from the
authenticated session, and records policy/decision/evidence digests. A release
review is a non-deployment evidence record. Mandatory validation uses disposable
PostgreSQL and Chromium with synthetic inputs only.

Onboarding actions call the same FastAPI/PostgreSQL routes used by the security
tests; the client cannot seed evaluations, decisions, cases, or release reviews.
Responsive and accessibility evidence is disposable Chromium output. Managed
customer identity, UI hosting, operational persistence, billing, and production
release governance remain unverified.

