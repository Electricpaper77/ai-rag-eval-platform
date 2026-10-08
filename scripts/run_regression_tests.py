#!/usr/bin/env python3
"""Run deterministic reliability regression cases and write CI gate evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.eval_harness import run_eval_harness


def main() -> int:
    output_path = Path("runs") / "agenttrust_regression_eval.jsonl"
    summary_path = Path("runs") / "agenttrust_regression_summary.json"
    summary = run_eval_harness(
        output_path=output_path,
        summary_path=summary_path,
        run_id="agenttrust-regression-ci",
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
