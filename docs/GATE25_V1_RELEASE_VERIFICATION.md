# Gate 25 — Non-Production v1.0.0 Release Verification

Gate 25 packages the already-validated AgentTrust IQ synthetic MVP. It freezes
product scope and adds no customer-facing backend capability. The exact source
commit is supplied at execution time as `GATE25_SOURCE_SHA`; the CI-generated
manifest is the source of truth for the tested SHA, command exit codes,
environment and evidence digests.

## Fresh checkout and reset

Prerequisites are Git, Python 3.11, Node 20, Docker with a Linux engine, and a
Chromium-capable host. No paid service, credential or customer data is needed.

Linux/macOS:

```bash
set -eu
export GATE25_SOURCE_SHA="$(git ls-remote origin refs/heads/main | cut -f1)"
git clone https://github.com/Electricpaper77/ai-rag-eval-platform.git agenttrust-iq
cd agenttrust-iq
git checkout --detach "$GATE25_SOURCE_SHA"
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt playwright
python -m playwright install --with-deps chromium
npm install --no-save --ignore-scripts axe-core@4.10.2
docker rm -f agenttrust-gate25-postgres 2>/dev/null || true
docker run --name agenttrust-gate25-postgres --rm -d \
  -e POSTGRES_PASSWORD=gate25 -e POSTGRES_DB=agenttrust \
  -p 5432:5432 postgres:16
trap 'docker rm -f agenttrust-gate25-postgres >/dev/null 2>&1 || true' EXIT
export AGENTTRUST_POSTGRES_URL=postgresql://postgres:gate25@localhost:5432/agenttrust
export AGENTTRUST_SAAS_DB=
export AGENTTRUST_SAAS_BACKEND=postgres
export AGENTTRUST_DEPLOYMENT_POLICY=test
export AGENTTRUST_SAAS_RUNTIME_MODE=test
export GATE23G_REQUIRED=1
python -c 'from saas.postgres_repository import migrate; migrate()'
timeout 600s python -m pytest -q tests/test_gate23g_acceptance.py -m postgres_integration --maxfail=1
python -m pytest -q tests/test_gate24_release_candidate.py -m release_candidate
```

PowerShell uses the same sequence and preserves exit codes with `$ErrorActionPreference = "Stop"`:

```powershell
$ErrorActionPreference = "Stop"
git clone https://github.com/Electricpaper77/ai-rag-eval-platform.git agenttrust-iq
Set-Location agenttrust-iq
$env:GATE25_SOURCE_SHA = (git ls-remote origin refs/heads/main).Split("`t")[0]
git checkout --detach $env:GATE25_SOURCE_SHA
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-test.txt playwright
& .\.venv\Scripts\python.exe -m playwright install chromium
npm install --no-save --ignore-scripts axe-core@4.10.2
docker rm -f agenttrust-gate25-postgres 2>$null; if ($LASTEXITCODE -notin 0,1) { exit $LASTEXITCODE }
docker run --name agenttrust-gate25-postgres --rm -d -e POSTGRES_PASSWORD=gate25 -e POSTGRES_DB=agenttrust -p 5432:5432 postgres:16
$env:AGENTTRUST_POSTGRES_URL = "postgresql://postgres:gate25@localhost:5432/agenttrust"
$env:AGENTTRUST_SAAS_DB = ""
$env:AGENTTRUST_SAAS_BACKEND = "postgres"
$env:AGENTTRUST_DEPLOYMENT_POLICY = "test"
$env:AGENTTRUST_SAAS_RUNTIME_MODE = "test"
$env:GATE23G_REQUIRED = "1"
& .\.venv\Scripts\python.exe -c "from saas.postgres_repository import migrate; migrate()"
& .\.venv\Scripts\python.exe -m pytest -q tests/test_gate23g_acceptance.py -m postgres_integration --maxfail=1
& .\.venv\Scripts\python.exe -m pytest -q tests/test_gate24_release_candidate.py -m release_candidate
docker rm -f agenttrust-gate25-postgres
```

If a prior run is interrupted, run only `docker rm -f agenttrust-gate25-postgres`
and repeat from a fresh disposable database. CI independently provisions and
tears down PostgreSQL; Windows execution has not been treated as Linux CI
evidence unless a recorded run says so.

## Acceptance and evidence

The real journey is callback-issued synthetic OIDC session → organization →
project → evaluation → persisted result → policy decision → investigation →
reviewer annotation → release review → authorized JSON/CSV export → refresh.
The Gate 23G browser suite also records 320, 390, 768 and 1440 pixel views,
keyboard/focus behavior, axe-core serious/critical results, 401/403/409/503
security responses, CSRF/origin enforcement, retry idempotency and quarantine.

Investigation rows created for this demonstration are deterministic fixtures and
must carry `synthetic_test`; they are not organic provider ingestion. Mock
evaluation output and GPU telemetry labels are simulated evidence, not provider
measurements or physical NVIDIA DCGM data.

`artifacts/gate25/release-manifest.json` records the exact source SHA, baseline,
workflow URL, environment, commands, exit codes, evidence paths and SHA-256
digests. It is generated only after the real acceptance files exist and rejects
known credential patterns. Missing evidence, non-zero exits or skipped mandatory
tests fail the workflow.

## Capability boundary and release decision

| Classification | Examples |
| --- | --- |
| Implemented | FastAPI SaaS routes, tenant authorization, persisted synthetic evidence, recovery quarantine |
| Independently tested | Disposable PostgreSQL HTTP path, Chromium journey, keyboard/focus, axe-core, refresh and security responses |
| Simulated | Controlled OIDC provider, mock evaluation provider, GPU telemetry labels |
| Unverified | Managed OIDC, production key custody, cloud backup/PITR, production RPO/RTO, physical DCGM metrics |

This is a non-production v1.0.0 release candidate. Commercial production remains
**NO-GO** pending managed identity, managed persistence, operational backup and
retention/deletion, observability and paging, privacy/legal review, billing
controls, deployment traffic management, recovery drills and physical GPU
validation. A technical acceptance result is not production authorization.
