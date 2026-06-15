# AgentTrust IQ Architecture

AgentTrust IQ evaluates reasoning-agent outputs against retrieved evidence and turns the result
into a deployment decision.

## Reliability Evaluation Flow

```mermaid
flowchart LR
    A[User Prompt] --> B[Reasoning Agent Output]
    B --> C[Retrieved Evidence / Policy Context]
    C --> D[AgentTrust IQ Reliability Gate]
    D --> E1[Groundedness Check]
    D --> E2[Citation Support Check]
    D --> E3[Hallucination Risk Check]
    D --> E4[PII Exposure Check]
    D --> E5[Latency Check]
    D --> E6[Audit Log Completeness Check]
    E1 --> F[Agent Readiness Score: 92]
    E2 --> F
    E3 --> F
    E4 --> F
    E5 --> F
    E6 --> F
    F --> G[Deployment Decision]
    G --> H[Approve / Fix / Escalate]
    H --> I[JSONL Audit Evidence]
    I --> J[Regression / CI Proof]
```

## Microsoft Foundry Production Pipeline

```text
GitOps -> IaC / Terraform -> DevOps -> AgentTrust IQ Reliability Gate -> Deploy or Block
```

AgentTrust IQ is the reliability and evaluation gate between production agent engineering and
deployment.

## Judge Proof

- [Live Command Center](https://ai-agent-reliability-platform-rtcd.vercel.app/agenttrust-iq-command-center.html)
- JSONL audit evidence
- Focused demo tests: **2 passed**
- Pytest collection: **128 tests collected**
- `git diff --check`: **passed**
