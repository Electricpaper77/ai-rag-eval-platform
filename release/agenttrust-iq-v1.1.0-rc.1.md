# AgentTrust IQ v1.1.0-rc.1 — Non-Production Release Candidate

This synthetic, reproducible package targets the exact feature commit recorded
by the Gate 25 manifest. It is not a production deployment, customer-access
release, billing release or cloud-operations attestation.

Follow [Gate 25 verification](../docs/GATE25_V1_RELEASE_VERIFICATION.md) from a
fresh checkout with disposable PostgreSQL and headless Chromium. No paid cloud
service or customer data is required.

The verified journey covers authenticated organization/project creation,
synthetic evaluation persistence, evidence-backed product workflows, tenant
authorization, CSRF/origin checks, responsive browser acceptance and restore
quarantine behavior.

Fixture-derived investigation rows carry `synthetic_test`. Mock provider output
and GPU labels are simulated; no live provider measurement or physical NVIDIA
DCGM metric is claimed. Historical AMD/ROCm references are not hardware evidence
for this release.

Remaining blockers include managed OIDC and key custody, production PostgreSQL,
cloud backup/PITR, retention/deletion operations, observability/paging, traffic
switching, incident drills, billing, privacy/legal review and customer support.
