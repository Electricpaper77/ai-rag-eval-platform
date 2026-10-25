# Gate 23A SaaS MVP

Open `/workspace` in the hosted static preview to use the non-production workspace shell. It provides dashboard, project, evaluation, result and settings views, responsive navigation, and a synthetic-data indicator. The evaluation action calls the existing authenticated FastAPI route; it does not create client-side identities or fabricate scores.

The browser test uses a disposable local HTTP server and Playwright at CI time. The authenticated PostgreSQL journey remains covered by the existing Gate 21 integration suite. Demo records are synthetic only, and API failures are shown as actionable states rather than converted into success.

Production blockers remain: managed OIDC deployment, customer UI hosting and operations, billing, managed persistence, retention/deletion/export operations, backup/PITR, production RPO/RTO, and physical GPU/DCGM validation.

## Gate 23C evaluation decisions

The workspace now exposes evidence-backed scorecards for synthetic evaluations. An
organization owner or admin creates an immutable, versioned policy; an authorized
member evaluates a persisted run against that policy and may compare it with an
authorized baseline. Decisions are `PASS`, `HOLD`, or `INSUFFICIENT_EVIDENCE`.
Only explicitly recorded evaluation metrics with authorized provenance are eligible
for a decision. Independently computed evidence is the secure default; synthetic
metrics require an explicitly labeled policy and isolated test deployment. Missing,
malformed, nonfinite, or untrusted metrics are shown as insufficient evidence, not
inferred or fabricated. Decision history
and JSON/CSV exports remain organization- and project-scoped and are protected by
the existing session, CSRF, tenant, and recovery-quarantine controls.

## Gate 23D investigation and release review

The investigation view lists only persisted per-case evidence. When no case rows
exist it renders `MISSING_EVIDENCE`; aggregate run scores are never converted into
case findings. Owner/admin reviewers append immutable, server-attributed review
revisions with `reviewer_confirmed` provenance and idempotency protection. Release
reviews snapshot the decision, policy version, run references, rationale and
evidence digest and are explicitly non-deployment records. Exports are tenant
scoped, sanitized and carry a non-production disclaimer. Gate 23D validation uses
synthetic PostgreSQL data and Chromium only.

\n+## Gate 23E product UX and demo readiness
\n+The authenticated workspace now provides a resumable, tenant-scoped first-run
journey: organization, project, evaluation, policy decision, investigation,
reviewer annotation, release review, and sanitized export. Progress is derived
from persisted API records; local storage contains only scoped identifiers and
never evidence or customer content. Missing case data remains `MISSING_EVIDENCE`.
Gate 23E validates 320px, 390px, 768px, and 1440px Chromium viewports, keyboard
focus, reduced-motion preferences, refresh persistence, cross-tenant denial, and
restore quarantine with disposable PostgreSQL and synthetic identities. This is a
non-production UX demonstration, not a customer-ready deployment.

