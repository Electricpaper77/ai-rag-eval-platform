from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.eval_harness import run_eval_harness


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local LLM evaluation proof harness.")
    parser.add_argument(
        "--output",
        default="docs/artifacts/eval_runs/hiring_eval.jsonl",
        help="JSONL artifact path for case rows and summary metrics.",
    )
    parser.add_argument(
        "--summary-output",
        default="docs/artifacts/eval_runs/hiring_eval_summary.json",
        help="Summary JSON artifact path.",
    )
    args = parser.parse_args()

    summary = run_eval_harness(output_path=args.output, summary_path=args.summary_output)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
