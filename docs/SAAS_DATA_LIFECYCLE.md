# Gate 22C data lifecycle contract

Tenant exports use schema `agenttrust-tenant-export-v1`, deterministic table order, a manifest with record counts, and organization-scoped relationship identifiers. Export requires an active owner or admin membership. Deletion requires an active owner membership and the exact `X-Deletion-Confirmation: DELETE <organization_id>` value; repeated requests by the original owner are idempotent.

Exports exclude `sessions`, `oidc_login_states`, raw bearer tokens, PKCE verifiers, Fernet keys, and other authentication secrets. Export and deletion requests write sanitized lifecycle audit records. Deletion is transactional: tenant-owned projects, runs, results, usage, and memberships are removed; the organization becomes an anonymized tombstone and lifecycle/audit evidence is retained. A controlled failure before the tombstone update rolls back and can be retried.

Retention defaults to 30 days, accepts only 1–3650 days, and supports dry-run counting. It currently cleans expired sessions and OIDC state. Scheduled execution is not installed.

Backups, CI artifacts, external object stores, identity-provider records, and third-party logs are outside this database workflow. A restored pre-deletion backup can reintroduce tenant data; reconciliation requires isolating the restore, re-running the deletion workflow, and recording the restore/deletion event. No claim of immediate permanent erasure from backups is made.
