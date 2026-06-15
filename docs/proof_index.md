# Proof Index

| Proof item | File path | What it proves | Hiring signal | Resume keyword |
|---|---|---|---|---|
| Current pytest validation | `README.md#validation-status` | Current local validation reports 2 focused AgentTrust tests passing, 128 tests collected, and a full-suite result of 99 passed, 28 failed, and 1 expected xfail. | Distinguishes reproducible judge proof from known legacy-suite failures. | Test automation |
| Historical security report | `docs/security_eval_report.md` | Preserves the methodology and recorded results of a historical security suite whose source fixture and dedicated tests are not present in this checkout. | Shows prior AI security evaluation design without presenting it as current reproducible proof. | AI security eval |
| Evidence integrity summary | `docs/artifacts/eval_summary.json` | Records per-artifact metrics and SHA256 checksums for the checked-in evaluation inputs. | Builds reviewer-verifiable evaluation proof. | Evidence integrity |
| JSONL eval logs | `docs/artifacts/eval_runs/eval_runs.jsonl` | Evaluation results are persisted as auditable JSONL records. | Knows how to create reviewable eval data. | JSONL audit logs |
| SHA256 artifact manifests | `docs/artifacts/eval_summary.json` | Eval metrics are linked to SHA256 checksums for each input JSONL artifact. | Can make metrics reproducible and tamper-evident. | SHA256 manifest |
| Prometheus metrics | `docs/artifacts/metrics_sample.txt` | Inference, eval, security, routing, and GPU metrics are exposed in Prometheus format. | Understands production observability. | Prometheus |
| Deployment packaging | `cloudbuild.yaml`, `Dockerfile`, `.gcloudignore`, `k8s/` | The repo includes Cloud Build, Docker, and Kubernetes packaging files; no active production cluster is claimed. | Can package AI services for cloud deployment. | Cloud Run, Kubernetes |
| RAG citations | `tests/test_agent_evaluation.py`, `app/evaluator.py` | Citation coverage is evaluated and missing citations are treated as failures. | Understands grounded-answer evaluation. | Citation precision |
| Historical PII-redaction methodology | `docs/security_eval_report.md` | Documents prior PII detection and redaction test design; the original validator and dedicated tests are not included. | Shows privacy-control design without presenting it as current reproducible proof. | PII redaction |
| Prompt-injection methodology | `docs/security_eval_report.md` | Documents historical prompt-injection and jailbreak-style test design; current source fixtures are not included. | Can design LLM red-team tests. | Prompt injection |
| GPU observability artifact | `docs/artifacts/gpu_observability_runs.jsonl` | Provides checked-in simulated GPU observability records. | Connects LLM eval with AI infrastructure evidence. | GPU observability |
| Canary rollback validation | `tests/test_canary_policy.py` | Canary routing and rollback behavior are covered by automated tests. | Understands safe rollout patterns. | Canary rollback |
| OpenAI-compatible inference observability | `tests/test_inference_observability_pipeline.py`, `backend/app/inference.py` | Chat completions persist structured request IDs, latency, TTFT, token, and status artifacts. | Builds inspectable OpenAI-compatible services. | Inference observability |
