# AgentTrust IQ 2.0 Architecture Diagram

Last verified against local working tree at base commit `5596c3b`.

```mermaid
flowchart TB
    User[User or CI request] --> API[FastAPI backend.app.main]
    API --> Chat[OpenAI-compatible chat endpoint]
    API --> Eval[/evaluate reliability endpoint]
    API --> Guarded[/query_guarded security endpoint]

    Chat --> Runtime[Mock or configured runtime adapter]
    Runtime --> Logs[Structured JSONL inference logs]

    Eval --> Evaluator[Deterministic evaluator]
    Evaluator --> Checks[Groundedness, citation precision, hallucination, refusal, PII, prompt injection]
    Checks --> EvalLogs[JSONL eval evidence with trace IDs, latency, throughput, cost estimate]
    EvalLogs --> Gate[Threshold gate: PASS, BLOCK, ESCALATE]

    Guarded --> Guardrails[Prompt-injection and PII redaction guardrails]
    Guardrails --> Retrieval[Local sample-doc retrieval]
    Retrieval --> GuardrailEvidence[Guardrail response and redacted context]

    EvalLogs --> Dashboard[Dashboard aggregation]
    Logs --> Metrics[Prometheus /metrics]
    Gate --> CI[GitHub Actions evaluation pipeline]
    Dashboard --> EvidenceDownloads[Downloadable evidence artifacts]
```

## Deployment Shape

- Static Vercel site: hosts the public walkthrough and Command Center HTML.
- FastAPI service: verified locally through tests and health checks; public API deployment is not claimed complete.
- CI gate: configured to run deterministic regression evaluation and threshold checks after push.

## Reliability Boundary

The production-quality claims in this repository are limited to reproducible local evidence until
the FastAPI service is deployed and independently verified in a public environment.
