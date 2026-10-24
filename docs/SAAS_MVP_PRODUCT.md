# Gate 23A SaaS MVP

Open `/workspace` in the hosted static preview to use the non-production workspace shell. It provides dashboard, project, evaluation, result and settings views, responsive navigation, and a synthetic-data indicator. The evaluation action calls the existing authenticated FastAPI route; it does not create client-side identities or fabricate scores.

The browser test uses a disposable local HTTP server and Playwright at CI time. The authenticated PostgreSQL journey remains covered by the existing Gate 21 integration suite. Demo records are synthetic only, and API failures are shown as actionable states rather than converted into success.

Production blockers remain: managed OIDC deployment, customer UI hosting and operations, billing, managed persistence, retention/deletion/export operations, backup/PITR, production RPO/RTO, and physical GPU/DCGM validation.

