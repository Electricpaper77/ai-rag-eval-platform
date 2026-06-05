# Recruiter Proof Guide

Use machine-readable artifacts as the primary evidence. Screenshots are supporting material and should only be added when they show current output from the documented commands.

## Primary Evidence

| Artifact | What it proves |
|---|---|
| `docs/artifacts/eval_runs/hiring_eval.jsonl` | Per-case records and summary row for the six-case controlled run |
| `docs/artifacts/eval_runs/hiring_eval_summary.json` | Headline hiring-run metrics with explicit scope labels |
| `docs/artifacts/eval_summary.json` | Combined 131-record metrics and SHA256 checksums |
| `docs/artifacts/eval_summary.md` | Human-readable evidence summary |
| `docs/artifacts/load_test_results.json` | Local load-test request, latency, and failure metrics |
| `docs/artifacts/metrics_sample.txt` | Prometheus-format metric output |
| `docs/artifacts/otel_traces.jsonl` | Request and backend trace evidence |
| `docs/security_eval_report.md` | Security evaluation methodology and results |
| `tests/test_eval_harness.py` | Evaluation artifact contract tests |

## Screenshot Policy

Only capture output after running the documented commands against the current working tree. Each screenshot should show:

- The relevant command or endpoint.
- The result body or test summary.
- The capture date.
- The commit SHA when the screenshot will be used publicly.

Do not use transient Cloud Shell URLs, staged failures, placeholder images, or screenshots whose metrics differ from the checked-in source artifact.

## Public Scope Language

Use this wording with screenshots or portfolio posts:

> Metrics are controlled fixture and local artifact results. They are not production traffic, live customer metrics, paid-provider benchmarks, or independent model comparisons.
