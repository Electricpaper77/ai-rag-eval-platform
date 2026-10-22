# AgentTrust IQ SaaS product gap analysis

Baseline: Gate 19 release `e7e7185835d681876adb2116dedb09b4ae3259b1`. The repository has a deterministic evaluator and evidence workflows, but no organization identity, durable customer database, tenant authorization, billing, or customer evaluation API.

| Priority | Gap | Status |
|---|---|---|
| P0 | Tenant identity and authorization | Local opaque configured identities implemented; production OIDC blocked |
| P0 | Durable tenant-owned records | SQLite migration-compatible slice implemented; managed PostgreSQL required |
| P0 | Customer journey | Organization → project → bounded JSONL evaluation → result/evidence implemented |
| P0 | Cross-tenant isolation | Organization-scoped project/run/result/usage queries tested |
| P1 | Async execution, retention/export, backups | Documented; not implemented |
| P1 | Stripe billing | Disabled; sandbox contract and signed webhooks pending |
| P2 | Customer dashboard/onboarding | Existing dashboard audited; SaaS UI pending |

Local SQLite is not production storage. The mock provider is not real model-provider execution. Prior GPU telemetry is simulated, not physical DCGM.
