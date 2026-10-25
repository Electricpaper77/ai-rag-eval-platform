# Gate 24 — Non-Production MVP v1.0 Release Candidate

Gate 24 freezes new SaaS features and packages the already implemented Gate
23A–23G product journey for independent engineering review. It is a synthetic,
non-production release candidate. The acceptance workflow starts from a clean
checkout, provisions disposable PostgreSQL, installs real Chromium, obtains
callback-issued test sessions, and exercises the existing FastAPI routes and
browser UI. It does not create customer identities or use a mock response layer.

## Acceptance boundary

| Area | Required evidence | Status boundary |
| --- | --- | --- |
| Setup | Clean checkout, pinned dependency files, migrations, bounded teardown | CI-tested procedure |
| Product journey | OIDC test callback → organization → project → evaluation → persisted result → policy decision → investigation → annotation → release review → export → refresh | Synthetic tenant data only |
| Security | Server-side session, CSRF/origin, tenant RBAC, idempotency, quarantine, export authorization | Disposable PostgreSQL/HTTP evidence |
| Accessibility | Keyboard focus, axe-core WCAG 2A/2AA, no serious/critical findings, 320/390/768/1440px screenshots | Chromium acceptance evidence |
| Evidence | Fixture provenance, missing-evidence states, SHA, exit codes and file hashes | Sanitized artifacts only |

The Gate 23G browser test inserts its investigation case directly as a
deterministic fixture. The persisted provenance is `synthetic_test`, and the
metadata says `fixture-only; not organic provider ingestion`. It is not a live
provider observation or a measured model-quality result.

## Fresh checkout: Linux/macOS

Prerequisites: Git, Python 3.11, Node 20, Docker, and a browser-capable local
runtime. No paid service or credential is required.

```bash
set -eu
git clone https://github.com/Electricpaper77/ai-rag-eval-platform.git
cd ai-rag-eval-platform
export GATE25_SOURCE_SHA="$(git ls-remote origin refs/heads/main | cut -f1)"
git checkout --detach "$GATE25_SOURCE_SHA"
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt playwright
python -m playwright install --with-deps chromium
npm install --no-save --ignore-scripts axe-core@4.10.2
docker rm -f agenttrust-gate24-postgres 2>/dev/null || true
docker run --name agenttrust-gate24-postgres --rm -d \
  -e POSTGRES_PASSWORD=gate24 -e POSTGRES_DB=agenttrust \
  -p 5432:5432 postgres:16
export AGENTTRUST_POSTGRES_URL=postgresql://postgres:gate24@localhost:5432/agenttrust
export AGENTTRUST_SAAS_DB=
export AGENTTRUST_SAAS_BACKEND=postgres
export AGENTTRUST_DEPLOYMENT_POLICY=test
export AGENTTRUST_SAAS_RUNTIME_MODE=test
export GATE23G_REQUIRED=1
trap 'docker rm -f agenttrust-gate24-postgres >/dev/null 2>&1 || true' EXIT
python -c "from saas.postgres_repository import migrate; migrate()"
python -m pytest -q tests/test_gate23g_acceptance.py -m postgres_integration --maxfail=1
python -m pytest -q tests/test_gate24_release_candidate.py -m release_candidate
docker rm -f agenttrust-gate24-postgres
```

The command returns exit code `0` only when all required tests and evidence
checks pass. A missing service, migration error, browser installation error,
failed assertion, or evidence validation error is non-zero. If an interrupted
run leaves the container behind, run `docker rm -f agenttrust-gate24-postgres`
before repeating the clean setup.

## Fresh checkout: Windows PowerShell

Use the same prerequisites and replace environment/export syntax with:

```powershell
$ErrorActionPreference = "Stop"
git clone https://github.com/Electricpaper77/ai-rag-eval-platform.git
Set-Location ai-rag-eval-platform
$env:GATE25_SOURCE_SHA = (git ls-remote origin refs/heads/main).Split("`t")[0]
git checkout --detach $env:GATE25_SOURCE_SHA
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-test.txt playwright
& .\.venv\Scripts\python.exe -m playwright install chromium
npm install --no-save --ignore-scripts axe-core@4.10.2
docker rm -f agenttrust-gate24-postgres 2>$null; if ($LASTEXITCODE -notin 0,1) { exit $LASTEXITCODE }
docker run --name agenttrust-gate24-postgres --rm -d -e POSTGRES_PASSWORD=gate24 -e POSTGRES_DB=agenttrust -p 5432:5432 postgres:16
$env:AGENTTRUST_POSTGRES_URL = "postgresql://postgres:gate24@localhost:5432/agenttrust"
$env:AGENTTRUST_SAAS_DB = ""
$env:AGENTTRUST_SAAS_BACKEND = "postgres"
$env:AGENTTRUST_DEPLOYMENT_POLICY = "test"
$env:AGENTTRUST_SAAS_RUNTIME_MODE = "test"
$env:GATE23G_REQUIRED = "1"
& .\.venv\Scripts\python.exe -c "from saas.postgres_repository import migrate; migrate()"
& .\.venv\Scripts\python.exe -m pytest -q tests/test_gate23g_acceptance.py -m postgres_integration --maxfail=1
& .\.venv\Scripts\python.exe -m pytest -q tests/test_gate24_release_candidate.py -m release_candidate
docker rm -f agenttrust-gate24-postgres
```

PowerShell preserves the Python exit code; a non-zero command stops the
acceptance sequence when invoked from the CI-equivalent wrapper. Do not put
real credentials in the environment or artifacts.

## Three-minute reviewer walkthrough

1. Start at the authenticated workspace and show the synthetic-only badge.
2. Create an organization and project through the UI; point out that the
   actions call the existing authenticated FastAPI/PostgreSQL routes.
3. Submit one synthetic evaluation, refresh, and open its persisted result.
4. Record a versioned policy decision and explain PASS/HOLD/
   INSUFFICIENT_EVIDENCE/MISSING_EVIDENCE states.
5. Open investigation, disclose the fixture-only case, save the reviewer
   annotation, create a non-production release review, and download sanitized
   JSON evidence.
6. Show the 320/390/768/1440px screenshots and the CI manifest. Emphasize that
   no provider performance, customer data, production RPO/RTO, billing, or
   physical GPU/DCGM result is represented.

## Release blockers and known limitations

- Managed OIDC deployment, customer hosting, live billing and customer data
  remain blocked.
- PostgreSQL evidence is disposable CI infrastructure; managed persistence,
  backup/PITR, retention/deletion operations, and production RPO/RTO remain
  unverified.
- Evaluation provider measurements are not claimed. Fixture rows are labeled
  `synthetic_test`; missing evidence remains explicit.
- Recovery quarantine and approval controls are tested locally, but production
  traffic switching, operator separation, paging and scheduled drills remain
  operational blockers.
- GPU labels are simulated evidence only. No physical NVIDIA DCGM measurement
  or production GPU performance claim is made.

The workflow writes the final commit SHA, actual test exit codes, sanitized
manifest and hashes of each evidence file. Gate 25 adds the final packaging
workflow and manifest; its artifact, not this document, is the source of truth
for final run counts and digests.
