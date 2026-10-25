# AgentTrust IQ

## What it does

AgentTrust IQ is a model-agnostic AI reliability and evaluation platform. It turns deterministic checks into explicit `release`, `block`, or `escalate` decisions with replayable JSONL evidence. The default path is local and reproducible without paid APIs.

## Key validated capabilities

- AI reliability checks for groundedness, citations, hallucination, refusal, prompt injection, PII, unsafe actions, latency, and auditability.
- Kubernetes workload lifecycle, scheduling/preemption, autoscaling/capacity controls, observability, incident validation, disaster recovery, supply-chain controls, distributed inference, and Linux/cgroup diagnostics.
- Secure runtime patterns including non-root containers, resource limits, restrictive policies, readiness probes, and bounded recovery checks.

## Evidence

The [Gate 17 evidence registry](evidence/infrastructure/gates.json) is the source of truth for capability status and evidence level. The [case study](docs/INFRASTRUCTURE_CASE_STUDY.md) and [evidence summary](docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md) provide recruiter-facing context. The canonical deterministic evaluation pack remains [`docs/artifacts/eval_runs/hiring_eval_summary.json`](docs/artifacts/eval_runs/hiring_eval_summary.json).

Canonical controlled evaluation result: **6 / 6 cases passed**, **100.0%** eval pass rate, **0.0%** hallucination rate, and **0.159 ms** evaluator p95. These are deterministic fixture measurements, not production or model-provider performance.

## Architecture

See the concise [system architecture](docs/ARCHITECTURE.md), including the FastAPI surface, evaluation layer, serving/router components, Kubernetes workloads, CI, observability, and evidence artifacts.

## Run locally

```bash
python -m pip install -r requirements-lite.txt
python scripts/verify_portfolio.py
python -m pytest -q tests/test_gate18_portfolio_release.py
```

For the application smoke path, start `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000` and use `python scripts/gate18_runtime_smoke.py --base-url http://127.0.0.1:8000`.

## Scope / limitations

This is a release candidate backed by CI and disposable validation environments; it does not claim production ownership or managed-cloud operations. AMD/ROCm hardware validation is implemented, but real GPU execution remains blocked pending access to qualifying AMD hardware.

## Verify AgentTrust IQ in 5 Minutes

Install the lightweight local dependencies:

```bash
python -m pip install -r requirements-lite.txt
```

Create the deterministic 50-case evidence pack (the requested `evaluations/` path is a stable alias for the checked-in NVIDIA-shaped fixture suite):

```bash
python -m app.eval.run --provider mock --suite evaluations/nvidia_eval_pack.jsonl --output artifacts/latest
```

The output is explicitly labeled **mock evidence**. It proves the deterministic evaluator and artifact contract, not NVIDIA/GPU, model, API, RAG, network, or production performance.

Run the focused verification:

```bash
python -m pytest tests/test_recruiter_evidence.py tests/test_nvidia_eval_pack.py -q
```

Open the dashboard:

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Then visit [http://127.0.0.1:8000/recruiter-evidence](http://127.0.0.1:8000/recruiter-evidence). Downloadable evidence is in `artifacts/latest/summary.json` and `artifacts/latest/results.jsonl` (or through the page links).

Start the deterministic API:

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Request the reliability workflow:

```bash
curl -s http://127.0.0.1:8000/demo/agenttrust-iq
```

Run the focused validation:

```bash
python -m pytest tests/test_agenttrust_demo.py -q
python -m pytest tests/test_eval_harness.py -q
```

Replay the deterministic audit trace:

```bash
python scripts/judge_replay.py
```

Optionally include Gemini-assisted evaluation:

```bash
GEMINI_API_KEY=your_api_key python scripts/judge_replay.py
```

The deterministic evaluator always runs and remains the fallback if Gemini is unconfigured or unavailable.

## Supporting proof

- [`PROOF.md`](PROOF.md) — short reviewer verification path.
- [`docs/artifacts/eval_runs/hiring_eval.jsonl`](docs/artifacts/eval_runs/hiring_eval.jsonl) — deterministic case records.
- [`tests/test_agenttrust_demo.py`](tests/test_agenttrust_demo.py) — demo response and JSONL contract.
- [`tests/test_eval_harness.py`](tests/test_eval_harness.py) — canonical evaluation artifact contract.

The frozen [Gate 24 MVP v1.0 release-candidate procedure](docs/GATE24_MVP_RELEASE_CANDIDATE.md) documents clean-checkout commands, the synthetic product journey, accessibility/security boundaries, and sanitized evidence requirements.

## Project Links

- [Static project walkthrough](https://ai-agent-reliability-platform-rtcd.vercel.app/)
- [AgentTrust IQ Command Center](https://ai-agent-reliability-platform-rtcd.vercel.app/agenttrust-iq-command-center.html)
- [GitHub repository](https://github.com/Electricpaper77/ai-rag-eval-platform)
- [Proof guide](PROOF.md)

## Resume-Safe Claim

Built AgentTrust IQ, a model-agnostic FastAPI agent reliability and evaluation platform with deterministic groundedness, citation, hallucination, refusal, prompt-injection, unsafe-action, and PII checks; produced replayable JSONL audit evidence and an explicit release, block, or escalate decision, with Gemini available only as an optional evaluator integration.

## Local distributed-systems evidence

The isolated [Gate 19 incident replay case study](docs/INCIDENT_REPLAY_CASE_STUDY.md) adds a FastAPI gateway, two local Go worker containers, trace propagation, structured logs, bounded failure injection, and reproducible baseline/degraded/recovery measurements. It preserves the Python/FastAPI evaluator. Metrics are claimed only from observed CI artifacts. GPU events are labeled simulated and are not physical DCGM measurements; local containers are not production infrastructure. See the [recruiter evidence summary](docs/RECRUITER_EVIDENCE_SUMMARY.md). The reproducible synthetic product acceptance is documented in [`docs/GATE23G_INDEPENDENT_ACCEPTANCE.md`](docs/GATE23G_INDEPENDENT_ACCEPTANCE.md).
