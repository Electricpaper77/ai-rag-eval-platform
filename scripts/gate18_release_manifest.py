"""Generate the tested release manifest from a terminal pytest result."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--regression", required=True)
    parser.add_argument("--output", default="release/agenttrust-iq-release.json")
    args = parser.parse_args()
    text = Path(args.regression).read_text(encoding="utf-8")
    passed = int(re.search(r"(\d+) passed", text).group(1))
    xfailed_match = re.search(r"(\d+) xfailed", text)
    xfailed = int(xfailed_match.group(1)) if xfailed_match else 0
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    result = {
        "name": "AgentTrust IQ",
        "baseline_sha": args.baseline_sha,
        "release_sha": sha,
        "test_total": passed,
        "xfailed": xfailed,
        "evidence_registry": "evidence/infrastructure/gates.json",
        "case_study": "docs/INFRASTRUCTURE_CASE_STUDY.md",
        "architecture": "docs/ARCHITECTURE.md",
        "blocked_items": ["Gate 13: qualifying AMD ROCm hardware unavailable"],
        "limitations": ["Release candidate only; no production deployment or real AMD GPU execution is claimed."],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
