# AgentTrust IQ Repository Manifest

This file is the quick-start contract for hackathon judges, reviewers, and AI coding agents.
Use it to understand the project, validate its proof, and avoid breaking judge-facing behavior.

## Project Identity

- **Project:** AgentTrust IQ
- **Positioning:** Reliability gate for Microsoft Foundry-style reasoning agents
- **Core claim:** Most hackathon agents show capability. AgentTrust IQ shows deployability.

## What The Project Does

AgentTrust IQ evaluates whether an agent answer is grounded, cited, safe, low-risk for
hallucination, and auditable before deployment. It produces an Agent Readiness Score and a
deployment decision: approve, fix, or escalate.

## Demo URLs

- **Live Command Center:** https://ai-agent-reliability-platform-rtcd.vercel.app/agenttrust-iq-command-center.html
- **Portfolio / home:** https://ai-agent-reliability-platform-rtcd.vercel.app/
- **GitHub repository:** https://github.com/Electricpaper77/ai-rag-eval-platform

## Judge Proof

| Signal | Verified value |
| --- | --- |
| Agent Readiness Score | **92** |
| Deployment Decision | **APPROVE WITH AUDIT EVIDENCE** |
| Groundedness | **PASS** |
| Citation Support | **PASS** |
| Hallucination Risk | **LOW** |
| PII Exposure | **NONE** |
| Audit Log | **COMPLETE** |

## Architecture

```text
User Prompt
  -> Reasoning Agent Output
  -> Retrieved Evidence
  -> AgentTrust IQ Reliability Gate
  -> Agent Readiness Score
  -> Deploy / Fix / Escalate
  -> JSONL Audit Evidence
```

## Microsoft Foundry Alignment

```text
GitOps -> IaC / Terraform -> DevOps -> AgentTrust IQ Reliability Gate -> Deploy or Block
```

AgentTrust IQ is the evaluation and release gate between production agent delivery and
deployment. It complements Microsoft Foundry-style engineering workflows with groundedness,
citation, safety, privacy, and audit checks.

## Validation Commands

Run from the repository root:

```bash
python -m pytest tests/test_agenttrust_demo.py
python -m pytest --collect-only
git diff --check
```

## Current Validation Status

- Focused demo tests: **2 passed**
- Focused demo tests: **2 passed**
- Pytest collection: **128 tests collected**
- `git diff --check`: **passed, CRLF warnings only**
- Live demo: **HTTP 200**
- GitHub link: **HTTP 200**

These values describe the latest submission QA pass. Re-run the validation commands after
changing code or judge-facing content.

## Do-Not-Break Rules

- Do not change the Agent Readiness Score unless the deterministic demo fixtures and assertions
  are updated together.
- Do not rename the Command Center anchors used by the video path: `score`,
  `foundry-pipeline`, `failure-case`, and `audit-proof`.
- Do not remove JSONL audit evidence references or the replayable audit record.
- Do not weaken Microsoft Foundry positioning.
- Do not add fake metrics or unsupported production claims.
- Do not add dependencies for visual polish.
- Preserve the existing deterministic demo behavior and proof values.

## Video Demo Path

```text
Hero -> Score 92 -> Foundry Pipeline -> Failure Case -> Judge Proof -> Final Decision
```

The Command Center exposes visible navigation for Score, Foundry Pipeline, Failure Case, and
Audit Proof. Use the Judge Proof strip between the failure case and final decision during a
recorded walkthrough.
