# Gemini API Usage Evidence

AgentTrust IQ supports the Gemini API for one optional LLM-based reliability evaluation workflow.
The existing deterministic evaluator remains the fallback and continues to work without an API key.

## Integration Proof

| Evidence | Location |
|---|---|
| Official Google GenAI SDK import and client call | `app/gemini_evaluator.py` |
| Gemini reliability evaluation CLI | `scripts/run_gemini_eval.py` |
| One-command judge replay | `scripts/judge_replay.py` |
| Mocked Gemini-path and deterministic-fallback tests | `tests/test_gemini_evaluator.py` |
| Sanitized JSONL schema example | `docs/artifacts/xprize/sample_gemini_eval.jsonl` |

`app/gemini_evaluator.py` imports `from google import genai` and calls
`client.models.generate_content(...)`. The structured evaluator scores groundedness, citation
support, hallucination risk, PII exposure risk, and prompt-injection risk, then returns a final
pass/fail recommendation.

## Configuration

Set these environment variables locally:

```bash
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-2.5-flash
```

`GEMINI_API_KEY` is required for a real Gemini call. `GEMINI_MODEL` is optional and defaults to
`gemini-2.5-flash`. No API key is committed to this repository.

## Generate Evidence

Run from the repository root:

```bash
python scripts/run_gemini_eval.py
```

The command writes one JSONL record to:

```text
docs/artifacts/xprize/gemini_eval_runs.jsonl
```

A real successful call is explicitly labeled with:

```json
{"evaluator_mode":"gemini","gemini_api_called":true,"provider":"google_gemini_api"}
```

The record also includes the configured model, Gemini response ID and model version when returned
by the SDK, token usage metadata when available, the structured assessment, and the deterministic
baseline. It never writes the API key.

If `GEMINI_API_KEY` is missing, the same command writes a clearly labeled deterministic fallback
record with `gemini_api_called: false`. The checked-in sample file is schema-only and is not
presented as proof of a real API call.

## Judge Replay

Run the reliability workflow, deterministic fallback, optional Gemini evaluator, and JSONL audit
output with one command:

```bash
python scripts/judge_replay.py
```

The replay writes `docs/artifacts/xprize/judge_replay_latest.jsonl`. Deterministic evaluation
always runs. If `GEMINI_API_KEY` is configured, the replay also attempts the Gemini evaluator and
sets `gemini_enabled: true` only after a successful API call.
