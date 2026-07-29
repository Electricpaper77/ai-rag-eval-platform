# Portfolio release validation

## Full-suite baseline comparison

Command on both branches: `python -m pytest -q` (using the repository's available virtual environment).

| Branch | Passed | Failed | Xfailed |
| --- | ---: | ---: | ---: |
| `main` | 104 | 28 | 1 |
| `feature/polish-flagship-portfolio` | 109 | 28 | 1 |

The 28 failed test names are identical on both branches. They cluster in evaluation API response contracts, benchmark and metrics endpoints/artifacts, canary routing, dashboard aggregation, GPU observability, inference routing/observability, health and streaming API contracts, and shadow logging. The feature branch introduces zero new failures.

The recruiter-facing change set is limited to static frontend content and styles; no evaluator, API, or test code was changed.
