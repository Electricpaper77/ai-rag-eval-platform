# AgentTrust IQ Judge Review

AgentTrust IQ is a reliability gate for Microsoft Foundry-style reasoning agents. It evaluates
whether an answer is supported, cited, safe, and auditable before deployment.

**AgentTrust IQ is not another chatbot. It is a deployment-readiness gate for reasoning agents.**

[Open the AgentTrust IQ Command Center](https://ai-agent-reliability-platform-rtcd.vercel.app/agenttrust-iq-command-center.html)

## Demo Highlights for Judges

1. Open the Command Center.
2. Review the governed question.
3. Review the retrieved evidence.
4. Review the cited answer.
5. Review the reliability checks.
6. Review the Agent Readiness Score.
7. Review the deployment decision.
8. Review the JSONL audit evidence.

## What To Click First

1. Open the [AgentTrust IQ Command Center](https://ai-agent-reliability-platform-rtcd.vercel.app/agenttrust-iq-command-center.html).
2. Read the first-screen Agent Readiness Score of **92** and deployment decision:
   **APPROVE WITH AUDIT EVIDENCE**.
3. Follow the visible video path: **Score -> Foundry Pipeline -> Failure Case -> Audit Proof**.
4. Use **Replay Audit Evidence** to restart the deterministic question-to-decision workflow.

## What To Look For

- **Groundedness:** Does the answer stay within the retrieved policy evidence?
- **Citation support:** Can each material claim be traced to a source?
- **Hallucination risk:** Does the answer add unsupported certainty or facts?
- **PII exposure:** Does the output reveal sensitive personal information?
- **Latency:** Is the check fast enough to act as a release gate?
- **Audit completeness:** Is the decision preserved as replayable JSONL evidence?

The demo failure case is intentionally concrete: an agent must not claim that refunds are always
approved within 24 hours when the policy only promises review within two business days and makes
approval conditional.

## Microsoft Foundry Deployment Fit

```text
GitOps -> IaC / Terraform -> DevOps
  -> AgentTrust IQ Reliability Gate -> Deploy or Block
```

Microsoft Foundry-style engineering explains how to package and ship agents through governed
software delivery. AgentTrust IQ supplies the missing evaluation gate: inspect retrieved evidence,
score the output, approve or block deployment, and preserve the decision for audit and regression
testing.

## Repository Proof

| Proof | File | What it demonstrates |
| --- | --- | --- |
| Judge packet | [`SUBMISSION_PACKET.md`](../SUBMISSION_PACKET.md) | One-page submission result, pitch, and rubric mapping |
| Agent/reviewer contract | [`AGENTS.md`](../AGENTS.md) | Proof values and do-not-break rules |
| Architecture | [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) | Reliability gate and Foundry pipeline diagrams |
| Demo implementation | [`backend/app/routes/agenttrust_demo.py`](../backend/app/routes/agenttrust_demo.py) | Deterministic evidence, checks, score, and JSONL output |
| Demo tests | [`tests/test_agenttrust_demo.py`](../tests/test_agenttrust_demo.py) | Endpoint and Command Center regression proof |
| Audit records | [`docs/artifacts/eval_runs/hiring_eval.jsonl`](artifacts/eval_runs/hiring_eval.jsonl) | Checked-in, replayable JSONL evaluation evidence |
| Broader evidence | [`docs/proof_index.md`](proof_index.md) | Evaluation, security, observability, and deployment artifacts |
| Submission metrics | [`evaluation_results.md`](../evaluation_results.md) | Submission benchmark scope and before/after metrics |

## Reproduce The Core Proof

Official judge validation:

```bash
python -m pytest tests/test_agenttrust_demo.py -q
```

Expected result: **2 focused AgentTrust demo tests passing**.

Supplemental repository checks:

```bash
python -m pytest --collect-only
git diff --check
```

Current discovery proof: **128 tests collected**. The full legacy suite currently includes
shared-fixture conflicts and is not the official judge validation path. Historical portfolio
materials reference **145+ passing tests**; today's reproducible hackathon proof is the focused
two-test path above.

## Known Limitations

- The demo uses a static deterministic fixture to make the judge flow repeatable.
- The focused judge tests validate the AgentTrust workflow and Command Center contract.
- The full legacy test suite requires fixture and application-entrypoint alignment before it can be
  represented as fully green.

## Judge Takeaway

Most agent demos prove that a model can answer. AgentTrust IQ proves whether the answer is ready
to deploy, needs a fix, or should be escalated, with evidence that can be replayed in CI and
reviewed after release.
