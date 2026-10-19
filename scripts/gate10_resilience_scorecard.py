"""Evaluate measured Gate 10 experiment results without synthesizing alerts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def score(experiments: list[dict[str, object]]) -> dict[str, object]:
    required = {"detected", "service_continuity", "recovered"}
    results = []
    for experiment in experiments:
        passed = required.issubset(experiment) and all(bool(experiment[key]) for key in required)
        results.append({**experiment, "passed": passed})
    overall = bool(results) and all(item["passed"] for item in results)
    return {"experiments": results, "overall": "PASS" if overall else "HOLD", "resilience": "PASS" if overall else "HOLD"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = score(json.loads(Path(args.input).read_text(encoding="utf-8")))
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RESILIENCE: " + result["resilience"])
    if result["resilience"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
