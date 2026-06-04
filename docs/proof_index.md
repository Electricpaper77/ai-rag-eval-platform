# Proof Index

| Proof item | File path | What it proves | Hiring signal | Resume keyword |
|---|---|---|---|---|
| Full pytest validation | `README.md#validation-status` | Current local validation reports 131 passing pytest checks and 1 expected xfail. | Can stabilize a multi-module AI platform test suite. | Test automation |
| Security eval tests | `tests/test_security_eval.py` | Deterministic red-team checks pass for prompt injection, PII, unsafe retrieval, malformed input, and related cases. | Practical AI security validation. | AI security eval |
| Evidence integrity tests | `tests/test_generate_eval_evidence.py` | Evidence summaries, per-artifact metrics, and SHA256 checksums are protected by tests. | Builds recruiter-verifiable evaluation proof. | Evidence integrity |
| JSONL eval logs | `docs/artifacts/eval_runs/eval_runs.jsonl` | Evaluation results are persisted as auditable JSONL records. | Knows how to create reviewable eval data. | JSONL audit logs |
| SHA256 artifact manifests | `docs/artifacts/eval_summary.json` | Eval metrics are linked to SHA256 checksums for each input JSONL artifact. | Can make metrics reproducible and tamper-evident. | SHA256 manifest |
| Prometheus metrics | `docs/artifacts/metrics_sample.txt` | Inference, eval, security, routing, and GPU metrics are exposed in Prometheus format. | Understands production observability. | Prometheus |
| Cloud Run / deployment evidence | `cloudbuild.yaml`, `Dockerfile`, `.gcloudignore`, `k8s/` | The repo includes Cloud Build, Docker, and Kubernetes packaging files. | Can package AI services for cloud deployment. | Cloud Run, Kubernetes |
| RAG citations | `tests/test_agent_evaluation.py`, `app/evaluator.py` | Citation coverage is evaluated and missing citations are treated as failures. | Understands grounded-answer evaluation. | Citation precision |
| PII redaction | `app/security/validators.py`, `docs/security_eval_report.md` | PII-like strings are detected and redacted or blocked in security cases. | Applies privacy controls to GenAI outputs. | PII redaction |
| Prompt-injection testing | `data/security_eval_prompts.jsonl`, `tests/test_security_eval.py` | Prompt injection and jailbreak-style cases are tested with expected safe actions. | Can design LLM red-team tests. | Prompt injection |
| GPU proof artifacts | `artifacts/proof/gpu_benchmark_run.jsonl`, `artifacts/proof/gpu_summary.json` | GPU benchmark harness writes proof-oriented run and summary artifacts. | Connects LLM eval with AI infrastructure evidence. | GPU observability |
| Canary rollback validation | `tests/test_canary_policy.py`, `artifacts/proof/canary_summary.json` | Canary routing and rollback behavior are tested and summarized. | Understands safe rollout patterns. | Canary rollback |
| OpenAI-compatible inference observability | `tests/test_inference_observability_pipeline.py`, `backend/app/inference.py` | Chat completions persist structured request IDs, latency, TTFT, token, and status artifacts. | Builds inspectable OpenAI-compatible services. | Inference observability |
