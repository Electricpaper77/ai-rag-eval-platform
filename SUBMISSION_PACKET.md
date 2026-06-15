# AgentTrust IQ: Reliability Gate for Microsoft Foundry-Style Agents

> AgentTrust IQ evaluates whether reasoning-agent outputs are grounded, cited, safe, low-risk
> for hallucination, and auditable before deployment.

**Core thesis:** Most hackathon agents show capability. AgentTrust IQ shows deployability.

## Live Links

- **Live Command Center:** https://ai-agent-reliability-platform-rtcd.vercel.app/agenttrust-iq-command-center.html
- **Portfolio:** https://ai-agent-reliability-platform-rtcd.vercel.app/
- **GitHub:** https://github.com/Electricpaper77/ai-rag-eval-platform

## Demo Result

| Judge signal | Result |
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
User Prompt -> Reasoning Agent Output -> Retrieved Evidence
  -> AgentTrust IQ Reliability Gate -> Agent Readiness Score
  -> Deploy / Fix / Escalate -> JSONL Audit Evidence
```

## Microsoft Foundry Alignment

```text
GitOps -> IaC / Terraform -> DevOps
  -> AgentTrust IQ Reliability Gate -> Deploy or Block
```

**Microsoft shows how to ship agents like real software. AgentTrust IQ shows how to trust them
like real software.**

## Technical Proof

- Focused AgentTrust IQ demo tests: **2 passed**
- Pytest collection: **128 tests collected**
- `git diff --check`: **passed, CRLF warnings only**
- Live demo: **HTTP 200**
- GitHub link: **HTTP 200**
- JSONL audit evidence included for replay and regression testing

## Judge Rubric Mapping

- **Accuracy & Relevance:** Checks answer support against retrieved evidence.
- **Reasoning Quality:** Evaluates whether the answer follows the evidence.
- **Reliability & Safety:** Checks hallucination risk, PII exposure, latency, and audit
  completeness.
- **UX & Presentation:** Command-center scorecard with approve, fix, or escalate decision.
- **Creativity:** Focuses on the trust layer, not another agent demo.

## Video Path

```text
Hero -> Score 92 -> Foundry Pipeline -> Failure Case -> Judge Proof -> Final Decision
```

## Final 20-Second Pitch

AgentTrust IQ is not another agent demo. It is the reliability gate that determines whether a
Microsoft Foundry-style reasoning-agent output should be approved, fixed, or escalated before
deployment.
