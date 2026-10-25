# AgentTrust IQ v1.0.0 — Non-Production Release Candidate

This package is a synthetic, reproducible portfolio release. It is not a
production deployment, customer-access release, billing release, or cloud
operations attestation.

## Reproduce

Follow [Gate 25 verification](../docs/GATE25_V1_RELEASE_VERIFICATION.md) from a
fresh checkout. Use the generated manifest's `source_sha` and retain command
exit codes. The required acceptance environment is disposable PostgreSQL plus
headless Chromium; no paid cloud service is required.

## Verified scope

The authenticated FastAPI journey persists synthetic evaluations and evidence,
enforces tenant authorization, protects cookie mutations with CSRF/origin
checks, and denies access while a restore target is quarantined. Browser
acceptance covers responsive layouts, keyboard focus, axe-core and refresh.

Fixture-derived investigation rows are explicitly `synthetic_test`; mock
provider output and GPU labels are simulated. No live provider measurement,
physical NVIDIA DCGM metric, production RPO/RTO or customer data is claimed.

## Remaining blockers

Managed OIDC and key custody, production PostgreSQL operations, cloud backup/
PITR and retention, deletion/export operations, observability/paging, traffic
switching, incident drills, billing, privacy/legal review and customer support
are outside this non-production release.
