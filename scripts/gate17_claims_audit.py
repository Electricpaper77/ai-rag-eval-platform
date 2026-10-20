"""Audit recruiter-facing claims against the Gate 17 evidence registry."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PATTERNS = {
    "production Kubernetes administration": re.compile(r"production\s+kubernetes\s+administration", re.I),
    "managed cloud Kubernetes": re.compile(r"managed\s+cloud\s+kubernetes", re.I),
    "production GPU fleet": re.compile(r"production\s+gpu\s+fleet", re.I),
    "AMD GPU workload execution": re.compile(r"amd\s+gpu\s+workload\s+execution", re.I),
    "MI300": re.compile(r"\bmi300\b", re.I),
    "multi-GPU inference": re.compile(r"multi[-\s]?gpu\s+inference", re.I),
    "production Slurm": re.compile(r"production\s+slurm", re.I),
    "zero downtime": re.compile(r"zero[-\s]?downtime", re.I),
    "production disaster recovery": re.compile(r"production\s+disaster\s+recovery", re.I),
}


def _supported(pattern_name: str, registry: dict[str, Any]) -> bool:
    levels = {entry.get("evidence_level") for entry in registry.get("gates", [])}
    if pattern_name in {"MI300", "AMD GPU workload execution", "multi-GPU inference", "production GPU fleet"}:
        return "REAL_HARDWARE" in levels
    if pattern_name.startswith("production") or pattern_name in {"managed cloud Kubernetes", "zero downtime"}:
        return "PRODUCTION" in levels
    return False


def audit_claims(registry: dict[str, Any], files: list[Path]) -> dict[str, Any]:
    unsupported: list[dict[str, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for name, pattern in PATTERNS.items():
            matches = list(pattern.finditer(text))
            if matches and not _supported(name, registry):
                # Explicit limitation language is evidence-safe: it prevents a
                # blocked capability from being presented as completed work.
                blocked_only = all(
                    re.search(r"(?:\bno\b|\bnot\b|\bnever\b|\bblocked\b|\bpending\b)", text[max(0, match.start() - 48):match.start()], re.I)
                    for match in matches
                )
                if blocked_only:
                    continue
                unsupported.append({"file": str(path), "claim": name})
    return {"status": "PASS" if not unsupported else "FAIL", "checked_files": [str(p) for p in files], "unsupported_claims": unsupported}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="evidence/infrastructure/gates.json")
    parser.add_argument("--claims-file", action="append", dest="claims_files")
    parser.add_argument("--output", default="artifacts/gate17/claims-audit.json")
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    files = [Path(value) for value in (args.claims_files or ["docs/INFRASTRUCTURE_CASE_STUDY.md", "docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md", "README.md"])]
    result = audit_claims(registry, files)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["status"] != "PASS":
        print(json.dumps(result, indent=2))
        return 1
    print("CLAIMS_AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
