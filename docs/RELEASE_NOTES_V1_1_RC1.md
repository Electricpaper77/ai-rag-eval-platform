# AgentTrust IQ v1.1.0-rc.1

## Release scope

This is a non-production, synthetic SaaS MVP release candidate targeting the
exact source SHA recorded in the Gate 25 release manifest. It is intended for
technical review and local reproduction; it is not a customer-access, billing,
or commercial production release.

## Verified scope

- Authenticated FastAPI and PostgreSQL SaaS journey.
- Tenant-scoped organizations, projects, evaluations and persisted evidence.
- Chromium acceptance with keyboard navigation, refresh persistence and
  responsive 320/390/768/1440 pixel evidence.
- CSRF/origin, unauthorized, cross-tenant, stale-revision and quarantine
  response checks.
- Sanitized JSON/CSV evidence export and fixture provenance labeling.

## Evidence boundary

Investigation rows are deterministic fixtures labeled `synthetic_test`; they are
not organic provider ingestion. Evaluation output and GPU telemetry labels are
simulated and are not provider measurements or physical NVIDIA DCGM data.
Historical AMD/ROCm references are not evidence of hardware execution for this
release.

## Production exclusions

This release does not claim managed OIDC, managed key custody, production
PostgreSQL operations, cloud backup/PITR, production RPO/RTO, observability and
paging, live billing, customer access, or physical GPU/DCGM validation.

Reproduce the package using the [Gate 25 v1.1.0-rc.1 verification procedure](GATE25_V1_RELEASE_VERIFICATION.md)
and the exact `source_sha` in its generated manifest.
