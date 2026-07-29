# Validation status

- Focused evidence validation: **9 tests passed**.
- Full suite at validation time: **109 passed, 28 failed, 1 xfailed**.
- Recruiter-facing changes introduced **zero new failures** against the documented repository baseline.

The 28 broader-suite failures are baseline issues in evaluation API contracts, benchmark and metrics endpoints/artifacts, canary routing, dashboard aggregation, GPU observability, inference routing, streaming/health API behavior, and shadow logging. They are not changed by the recruiter-facing static frontend work.
