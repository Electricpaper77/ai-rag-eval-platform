# AI RAG Threat Model

## Scope

This threat model covers the local RAG evaluation platform, including user prompts, retrieved context, generated model responses, evaluation datasets, JSONL audit artifacts, and metrics endpoints.

## Assets

| Asset | Why It Matters |
|---|---|
| User prompts | May contain sensitive personal, business, or operational data. |
| Retrieved documents | May include confidential policy, support, or operational content. |
| Model responses | Can leak sensitive strings or unsupported claims if not validated. |
| Guardrail decisions | Provide audit evidence for security and reliability behavior. |
| Evaluation datasets | Recruiter-visible proof of adversarial coverage. |
| Metrics and artifacts | Demonstrate control effectiveness and regression history. |

## Attack Surfaces

| Surface | Example Risk |
|---|---|
| `/v1/chat/completions` | Malicious user prompt attempts to override system or developer instructions. |
| RAG retrieval context | Retrieved text includes sensitive or irrelevant content that the model may over-trust. |
| `/evaluate` and eval datasets | Unsafe responses may be scored as acceptable if checks are incomplete. |
| Logs and JSONL artifacts | PII or secrets can persist if responses are not redacted before logging. |
| `/metrics` | Metrics can reveal control gaps if not monitored or can drift if not tested. |

## Threats

| Threat | Impact | Control |
|---|---|---|
| Prompt injection | Hidden instructions or policy controls are overridden. | Regex-based prompt injection detection with `prompt_injection` reason codes. |
| System prompt leakage | Internal instructions are disclosed to users. | Blocks reveal/show/dump requests for system and developer messages. |
| PII leakage | Email, phone, SSN-like, payment-card-like, or secret-like strings appear in output. | Deterministic redaction and redaction success tests. |
| Unsafe retrieval | Confidential retrieved snippets are exposed or used to bypass authorization. | Sensitive-context detection plus unsafe request classification. |
| Malformed input | Empty, non-string, control-character, or malformed structured input reaches retrieval. | Pre-retrieval rejection with `malformed_input`. |
| Irrelevant-context abuse | Model answers unsupported questions using unrelated context. | Lexical relevance check with `irrelevant_context` blocking behavior. |
| Silent regression | Future edits weaken the security layer without visibility. | Pytest suite and Prometheus metric names for pass rate, block rate, redaction success, unsafe response rate, and malformed rejection count. |

## Controls

- `app/security/validators.py` returns structured actions and reason codes.
- `data/security_eval_prompts.jsonl` provides 31 deterministic adversarial cases.
- `tests/test_security_eval.py` validates expected safe behavior and exports a pass/fail summary.
- Security metrics are added to the project metrics modules.
- `docs/security_eval_report.md` documents methodology, sample results, and OWASP LLM Top 10 mapping.

## Residual Risks

- Regex validation is intentionally simple and should be supplemented with model-based or policy-engine checks in production.
- Lexical context relevance can miss semantic mismatch or adversarially similar wording.
- PII detection covers common patterns but not all personal data types.
- The suite validates defensive behavior but does not replace human red-team review.
- External model behavior is not tested here; this layer is a deterministic preflight and regression harness.

## Next Controls

- Add model-graded safety evals behind a deterministic fixture mode.
- Store redacted audit logs by default and keep raw traces out of recruiter-facing artifacts.
- Add CI thresholds for minimum `security_eval_pass_rate` and maximum `unsafe_response_rate`.
- Expand context relevance checks with embeddings when a portable vector backend is available.
