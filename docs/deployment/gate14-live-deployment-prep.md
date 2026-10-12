# Gate 14 Live Deployment Preparation

Status: preparation only. No GCP resources, secrets, billing settings, Cloud Run services, public IAM bindings, or deployments were created.

Baseline commit: `cc3076dca67ff244282be77a1282c348d9f65c9e`

## Readiness Assessment

AgentTrust IQ is ready for a controlled Cloud Run deployment review, not an automatic public launch.

Read-only GCP authorization preflight on 2026-10-11:

- Configured project: `ai-rag-eval-prod`
- Project number: `69725201265`
- Project state: `ACTIVE`
- Configured region: `us-central1`
- Active Google Cloud identity: `azohaib.0150@gmail.com`
- Active identity project role visible from IAM policy: `roles/owner`
- Linked billing account: `billingAccounts/01D89A-FBE95E-85B909`
- Billing account display name: `My Billing Account`
- Billing account open: `false`
- Project billing enabled: `false`
- Required APIs currently enabled: `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com`, `run.googleapis.com`
- Required APIs not confirmed enabled: `secretmanager.googleapis.com`, `billingbudgets.googleapis.com`
- Runtime service account `agenttrust-iq-api@ai-rag-eval-prod.iam.gserviceaccount.com`: not found
- Secret `agenttrust-api-key`: not readable/listable because the project consumer is suspended
- Cloud Run services in `us-central1`: not readable/listable because the project consumer is suspended
- Artifact Registry repositories in `us-central1`: not readable/listable because the project consumer is suspended
- Budget alerts: not verified because `billingbudgets.googleapis.com` is disabled and the billing account is closed

Blocking conclusion:

- Live deployment cannot proceed until billing is reopened/enabled for `ai-rag-eval-prod` and budget-alert visibility is confirmed. Budget alerts notify on spend thresholds; they do not impose a hard spending cap.

Verified:

- Six GitHub Actions workflows passed on `main`.
- Production CI passed with `212 passed, 1 xfailed`.
- Regression harness passed `6/6`.
- Release gate passed.
- Linux Docker build passed.
- Linux container runtime smoke passed `/health`, `/metrics`, `/openapi.json`, valid `/evaluate`, invalid request handling, and request-id tracing.
- Production safe mode is available with `AGENTTRUST_REQUIRE_API_KEY=true`.
- Cloud Run deployment guidance is private-by-default with `--no-allow-unauthenticated`.

Not yet executed:

- GCP project setup.
- Artifact Registry creation.
- Secret Manager secret creation.
- Cloud Run service deployment.
- External HTTP smoke test against a live Cloud Run URL.
- Public frontend integration against a live backend.

## Configuration Audit

### Container

- `Dockerfile` uses `python:3.11-slim`, installs `requirements.txt`, copies the repository, and starts `backend.app.main:app` with Gunicorn/Uvicorn on `$PORT`.
- `PORT=8080` is set for Cloud Run compatibility.
- Existing CI verifies the image builds and starts on Ubuntu.
- Docker currently uses shell-form `CMD`, which CI reports as a warning only. It is not blocking, but JSON-form `CMD` would improve signal handling in a future hardening pass.

### Cloud Run YAML

Prepared file: `infra/cloudrun/agenttrust-api-service.yaml`

Key settings:

- Service: `agenttrust-iq-api`
- Image: `us-central1-docker.pkg.dev/PROJECT_ID/rag-eval-repo/agenttrust-iq-api:IMAGE_TAG`
- Runtime identity: `agenttrust-iq-api@PROJECT_ID.iam.gserviceaccount.com`
- `containerConcurrency: 10`
- `timeoutSeconds: 120`
- CPU: `1`
- Memory: `1Gi`
- Min scale: `0`
- Max scale: `2`
- Startup and liveness probes: `/health`
- Secret Manager reference: `AGENTTRUST_API_KEY=agenttrust-api-key:latest`

Caveat:

- `run.googleapis.com/ingress: all` allows ingress reachability, but Cloud Run IAM still blocks callers unless invoker permission is granted. Keep `--no-allow-unauthenticated`; do not bind `allUsers` to `roles/run.invoker` without a separate security review.

### Authentication

Two layers are required:

1. Cloud Run IAM: caller must present a valid identity token for direct service access.
2. Application API key: protected app routes require `X-AgentTrust-API-Key`.

Application-level public path:

- `/health`

Protected by application key when `AGENTTRUST_REQUIRE_API_KEY=true`:

- `/metrics`
- `/openapi.json`
- `/docs`
- `/redoc`
- `/evaluate`
- `/v1/chat/completions`
- `/dashboard/*`
- `/api/*`
- `/platform/*`
- `/eval/*`
- `/gpu/status`
- `/benchmark/*`

### Secret Handling

- Required API key is stored in Secret Manager as `agenttrust-api-key`.
- Runtime service account should receive only `roles/secretmanager.secretAccessor` on that one secret.
- The Cloud Run smoke script accepts the identity token through `CLOUD_RUN_IDENTITY_TOKEN` or `-IdentityToken` and does not print it.
- The smoke script sends the app key separately as `X-AgentTrust-API-Key` and does not print it.
- `.dockerignore` excludes `.env`, `.aws`, `.codex`, `.agents`, `artifacts`, `runs`, and `docs/artifacts`.

### Frontend Integration

- `frontend/agenttrust-iq-command-center.html` uses relative API paths and is compatible with a same-origin backend.
- `frontend/streamlit_app.py` hardcodes `http://127.0.0.1:8000`; do not claim production frontend readiness for this Streamlit app until it is made configurable.

## Exact Commands Prepared

Set variables:

```bash
export PROJECT_ID="your-gcp-project"
export REGION="us-central1"
export REPOSITORY="rag-eval-repo"
export SERVICE="agenttrust-iq-api"
export IMAGE_TAG="cc3076d"
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$SERVICE:$IMAGE_TAG"
```

Enable APIs after explicit billing/project approval:

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com
```

Create Artifact Registry repository:

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION" \
  --description="AgentTrust IQ container images"
```

Create least-privilege runtime service account:

```bash
gcloud iam service-accounts create agenttrust-iq-api \
  --display-name="AgentTrust IQ Cloud Run runtime"
```

Create the application API-key secret:

```bash
openssl rand -base64 32 | \
  gcloud secrets create agenttrust-api-key --data-file=-
```

Grant the runtime identity access only to that secret:

```bash
gcloud secrets add-iam-policy-binding agenttrust-api-key \
  --member="serviceAccount:agenttrust-iq-api@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

Build and push immutable image:

```bash
gcloud builds submit --tag "$IMAGE"
```

Deploy private Cloud Run service:

```bash
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "agenttrust-iq-api@$PROJECT_ID.iam.gserviceaccount.com" \
  --no-allow-unauthenticated \
  --set-env-vars "PORT=8080,INFERENCE_BACKEND=mock,AGENTTRUST_REQUIRE_API_KEY=true,ARTIFACT_DIR=/tmp/agenttrust-artifacts,DEPLOYMENT_ENVIRONMENT=production,OTEL_SERVICE_NAME=agenttrust-iq-api" \
  --set-secrets "AGENTTRUST_API_KEY=agenttrust-api-key:latest" \
  --cpu 1 \
  --memory 1Gi \
  --concurrency 10 \
  --timeout 120 \
  --min-instances 0 \
  --max-instances 2 \
  --no-cpu-boost
```

Validation:

```bash
export BASE_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
export CLOUD_RUN_IDENTITY_TOKEN="$(gcloud auth print-identity-token)"
export AGENTTRUST_API_KEY="$(gcloud secrets versions access latest --secret=agenttrust-api-key)"
pwsh ./scripts/smoke_gate13_cloudrun.ps1 -BaseUrl "$BASE_URL" -ApiKey "$AGENTTRUST_API_KEY"
```

Rollback:

```bash
gcloud run revisions list --service "$SERVICE" --region "$REGION"
gcloud run services update-traffic "$SERVICE" \
  --region "$REGION" \
  --to-revisions "PREVIOUS_REVISION=100"
```

Emergency public-access removal:

```bash
gcloud run services remove-iam-policy-binding "$SERVICE" \
  --region "$REGION" \
  --member="allUsers" \
  --role="roles/run.invoker"
```

## Deployment Validation Matrix

| Check | Expected |
| --- | --- |
| IAM-authorized `/health` | HTTP 200 |
| No IAM identity token to direct Cloud Run URL | HTTP 403 |
| IAM-authorized `/metrics` without app key | HTTP 401 |
| IAM-authorized `/metrics` with invalid app key | HTTP 401 |
| IAM-authorized `/metrics` with valid app key | HTTP 200 |
| IAM + valid app key `/evaluate` | HTTP 200 with `run_id` |
| Request-id tracing | JSONL evidence contains matching trace/request IDs |
| Secret exposure | Smoke output does not print identity token or app key |
| Revision health | Cloud Run revision ready and receiving intended traffic |

## Architecture Diagram

```mermaid
flowchart LR
    Dev[Developer / CI] --> Build[Cloud Build]
    Build --> Registry[Artifact Registry\nagenttrust-iq-api:cc3076d]
    Registry --> Run[Cloud Run private service\nagenttrust-iq-api]
    Secret[Secret Manager\nagenttrust-api-key] --> Run
    Caller[Authorized caller\nIAM identity token] --> Run
    Run --> Auth[App API-key middleware\nAGENTTRUST_REQUIRE_API_KEY=true]
    Auth --> Health[/health]
    Auth --> Eval[/evaluate]
    Auth --> Metrics[/metrics]
    Auth --> Router[/v1/chat/completions]
    Eval --> Logs[JSONL evidence\n/tmp/agenttrust-artifacts]
    Router --> Logs
```

## CI Evidence Summary

Commit: `cc3076dca67ff244282be77a1282c348d9f65c9e`

- CI Smoke Test: passed.
- AgentTrust Focused Validation: passed.
- Recruiter Evidence Pack: passed.
- GPU Benchmark: passed; mock/server-unavailable records are not real GPU performance evidence.
- AgentTrust Container Runtime Smoke: passed.
- AgentTrust Production CI: passed.
- Full pytest: `212 passed, 1 xfailed`.
- Regression harness: `6/6`, pass rate `100%`.
- Release gate: `PASS`.
- Production CI Docker image: `sha256:19e18e2cac382c733dc5c5fdff10a093b2e0cf4aedc934c727cb34a906ff403c`.
- Container runtime smoke Docker image: `sha256:4234f8b08a6ce4e6e5a3bb8ad29dab771e06e84c901770cb065799e0de5be446`.

## Security Controls Summary

- Private-by-default Cloud Run deployment.
- No `allUsers` invoker binding in prepared commands.
- App-level API key required for protected routes.
- Secret Manager stores application API key.
- Runtime service account receives least-privilege secret access only.
- `/metrics`, `/openapi.json`, docs, dashboards, traces, artifacts, and admin/control routes are protected.
- CI artifacts were adjusted to avoid raw environment dumps from `docker inspect`.
- Runtime smoke validates request-id tracing and invalid request handling.

## Reproducible Test Report

Post-merge CI on `main`:

```text
pytest: 212 passed, 1 xfailed
regression harness: 6/6
release gate: PASS
container runtime smoke: PASS
docker build: PASS
```

Local-safe predeployment command set:

```bash
python -m pip check
python -m compileall -q app backend gpu_platform scripts tests
python scripts/run_regression_tests.py
python scripts/check_eval_thresholds.py --artifact runs/agenttrust_regression_eval.jsonl
```

## 90-Second Technical Demo

1. "AgentTrust IQ is a production-style reliability platform for LLM and agent evaluation. The core FastAPI service exposes deterministic evaluation, OpenAI-compatible inference, release gates, observability, and evidence artifacts."
2. "The quality gate is real: CI runs dependency checks, Python compilation, regression evals, release-threshold enforcement, full pytest, Docker build, and Linux container runtime smoke."
3. "For deployment, the Cloud Run plan is private by default. Cloud Run IAM protects the service boundary, while an application API key protects metrics, traces, dashboards, evaluation endpoints, and control-plane routes."
4. "The smoke test proves the security split: no IAM token is denied by Cloud Run, missing or invalid app keys return 401 for protected routes, and valid IAM plus valid app key can run an authenticated evaluation."
5. "Every displayed metric is tied to reproducible CI artifacts. The latest verified run has 212 passing tests, 1 expected xfail, 6/6 regression cases, a passing release gate, and a Linux container runtime proof."
6. "I did not claim real GPU throughput from mock or unavailable benchmark records; those remain schema and readiness evidence only."

## ATS-Ready Resume Bullets

- Built AgentTrust IQ, a production-style LLM reliability platform with deterministic evaluation for groundedness, citation precision, refusal accuracy, prompt-injection handling, and release-gate enforcement; verified in CI with `212 passed, 1 xfailed` and `6/6` regression cases.
- Containerized and validated a FastAPI evaluation service on Linux with GitHub Actions Docker build and runtime smoke tests covering `/health`, `/metrics`, `/openapi.json`, valid evaluation, invalid request handling, and request-id trace evidence.
- Designed a private-by-default Cloud Run deployment plan using IAM, Secret Manager, application API-key middleware, least-privilege runtime identity, resource caps, rollback commands, and smoke tests that distinguish Cloud Run `403` from application `401` failures.

## Cost Drivers And Controls

Cost drivers:

- Cloud Build minutes.
- Artifact Registry image storage.
- Cloud Run request count, CPU, memory, and outbound network.
- Secret Manager storage/access.
- Cloud Logging volume.
- Optional future model-provider or GPU-serving costs.

Controls:

- `min-instances=0`.
- `max-instances=2`.
- `cpu=1`.
- `memory=1Gi`.
- `concurrency=10`.
- `INFERENCE_BACKEND=mock` until external backends are separately approved.
- Budget alerts should be configured before deployment.
- Use immutable image tags and rollback by revision.

## Remaining Blockers

- GCP project `ai-rag-eval-prod` and region `us-central1` are configured locally, but billing is disabled and the linked billing account is closed.
- Project consumer state is suspended for paid/resource APIs, blocking Cloud Run, Secret Manager, and Artifact Registry inventory/deployment.
- Budget alerts are not verified; `billingbudgets.googleapis.com` is not enabled. Budget alerts are notifications only and do not hard-stop spending.
- No Artifact Registry repository exists from this preparation step.
- No Secret Manager secret exists from this preparation step.
- No Cloud Run service or IAM policy has been created.
- Streamlit frontend still has a local `127.0.0.1` API base and is not production-backend ready without configuration.
- If public access is desired, API Gateway or HTTPS Load Balancer design still requires explicit approval.

## Required Live-Deployment Approvals

1. GCP project ID and billing account.
2. Region, recommended `us-central1`.
3. Permission to enable required Google APIs.
4. Permission to create or reuse Artifact Registry repository `rag-eval-repo`.
5. Permission to create runtime service account `agenttrust-iq-api`.
6. Permission to create Secret Manager secret `agenttrust-api-key`.
7. Permission to grant only `roles/secretmanager.secretAccessor` on that secret to the runtime service account.
8. Permission to run Cloud Build and push immutable image `agenttrust-iq-api:cc3076d`.
9. Permission to deploy private Cloud Run service with `--no-allow-unauthenticated`.
10. Separate approval for any public ingress, custom domain, API Gateway, HTTPS Load Balancer, or `allUsers` invoker exception.
