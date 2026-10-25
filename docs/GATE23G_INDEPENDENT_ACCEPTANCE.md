# Gate 23G — Independent Product Acceptance

This is a reproducible, zero-paid-cloud acceptance procedure for the synthetic
AgentTrust IQ SaaS demo. It uses the real FastAPI application, disposable
PostgreSQL, callback-issued test sessions and headless Chromium. It does not
use customer data, live providers, billing, managed infrastructure or physical
GPU/DCGM measurements.

## Fresh-checkout procedure

Prerequisites: Git, Python 3.11, Node 20, Docker with the Linux engine, and
approximately 2 GB of disposable disk space. Expected command exit codes are
shown explicitly; any non-zero code is a failed acceptance.

```bash
git clone https://github.com/Electricpaper77/ai-rag-eval-platform.git
cd ai-rag-eval-platform
git checkout feature/gate23g-independent-product-acceptance
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt playwright                 # 0
python -m playwright install --with-deps chromium                          # 0
npm install --no-save --ignore-scripts axe-core@4.10.2                    # 0
docker run -d --rm --name agenttrust-gate23g-postgres -e POSTGRES_PASSWORD=gate23g \
  -e POSTGRES_DB=agenttrust -p 5432:5432 postgres:16                    # 0; detached
export AGENTTRUST_POSTGRES_URL=postgresql://postgres:gate23g@localhost:5432/agenttrust
export AGENTTRUST_SAAS_DB=
export AGENTTRUST_SAAS_BACKEND=postgres
export AGENTTRUST_DEPLOYMENT_POLICY=test
export AGENTTRUST_SAAS_RUNTIME_MODE=test
export GATE23G_REQUIRED=1
python -c 'from saas.postgres_repository import migrate; migrate()'             # 0
timeout 600s python -m pytest -q tests/test_gate23g_acceptance.py \
  -m postgres_integration --maxfail=1                                        # 0
```

PowerShell users should set the same variables with `$env:NAME = "value"` and
use `docker run -d`; stop and remove the disposable container after the run.
The test fixture supplies a controlled OIDC provider and obtains sessions only
through `/saas/auth/login` and `/saas/auth/callback`. It never inserts a session
or identity directly.

## Tested journey

The mandatory test suite executes:

1. callback-issued authentication and tenant-scoped organization/project creation;
2. synthetic evaluation submission, PostgreSQL persistence, result detail and
   idempotent retry;
3. versioned policy decision, case investigation and reviewer annotation;
4. release review and JSON/CSV evidence export;
5. refresh persistence, keyboard focus recovery and 320/390/768/1440-pixel
   Chromium screenshots;
6. axe-core WCAG 2A/2AA audit, failing on serious or critical violations;
7. 401 unauthenticated access, missing-CSRF rejection, 403/404 cross-tenant
   denial, 409 stale revision, 503 quarantine, malformed JSON and network retry;
8. sanitized evidence generation with fixture provenance explicitly labeled
   `synthetic_test`; the evidence metadata separately states that the row is a
   fixture and not provider measurement.

The case rows used to demonstrate investigation are inserted as deterministic
fixture rows and are not claimed to originate from organic evaluation ingestion.
Evaluation records and API results are created through the actual HTTP routes.

## CI evidence contract

`.github/workflows/gate23g-independent-product-acceptance.yml` provisions
PostgreSQL, installs Chromium and axe-core, applies migrations, requires exactly
three collected Gate 23G tests, records their exit code, and uploads
`artifacts/gate23g/` with `if-no-files-found: error`. Missing browser,
PostgreSQL, test collection, screenshots or JSON evidence fails the workflow;
there is no silent skip path when `GATE23G_REQUIRED=1`.

## Reset and troubleshooting

Use a new disposable PostgreSQL container/database for every run. If migration
or authentication state persists, stop and remove only the named disposable
container, then rerun. A 503 indicates restore quarantine or unavailable
persistence; a 401/403 indicates authentication or tenant authorization; a 409
indicates a stale revision and must not be retried with a new mutation key.
Docker or Chromium installation failures are environment blockers, not passing
acceptance evidence.

## Capability boundaries

| Category | Status |
|---|---|
| FastAPI/PostgreSQL HTTP journey | Implemented and tested locally in CI |
| Browser onboarding and evidence workflow | Implemented and tested with Chromium in CI |
| Accessibility | axe-core WCAG 2A/2AA serious/critical gate tested in CI |
| OIDC | Controlled synthetic test provider; production IdP remains unconfigured |
| Evaluation provider metrics | Synthetic/mock evidence only; no live LLM measurement claim |
| GPU telemetry | Simulated labels only; not physical NVIDIA DCGM |
| Production operations | No deployment, billing, customer access, RPO/RTO or paid cloud validation |
