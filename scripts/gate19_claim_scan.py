"""Scan portfolio-facing text for claims beyond the Gate 17 evidence boundary."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PATTERNS = {
    "production-scale": re.compile(r"production[-\s]?scale", re.I),
    "production Kubernetes": re.compile(r"production\s+kubernetes", re.I),
    "production Slurm": re.compile(r"production\s+slurm", re.I),
    "AMD GPU validated": re.compile(r"amd\s+gpu\s+(?:execution|validated|workload)", re.I),
    "MI300": re.compile(r"\bmi300(?:\s+execution)?\b", re.I),
    "multi-GPU": re.compile(r"multi[-\s]?gpu", re.I),
    "zero downtime": re.compile(r"zero[-\s]?downtime", re.I),
    "production disaster recovery": re.compile(r"production\s+disaster\s+recovery", re.I),
}
TEXT_SUFFIXES = {".md", ".json", ".txt", ".yaml", ".yml"}


def _limitation_context(text: str, match: re.Match[str]) -> bool:
    start = max(0, match.start() - 100)
    context = text[start:match.start()]
    following = text[match.end():min(len(text), match.end() + 100)]
    section = text[:match.start()].split("\n")[-12:]
    nearby = " ".join(section) + " " + context + " " + following
    return bool(re.search(r"\b(?:no|not|never|blocked|pending|unavailable|unvalidated|not\s+claimed)\b", nearby, re.I)) or "NOT CLAIMED" in nearby.upper() or "KNOWN LIMITATIONS" in nearby.upper()


def scan_claims(registry: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
    levels = {entry.get("evidence_level") for entry in registry.get("gates", [])}
    findings: list[dict[str, str]] = []
    checked: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES]
        for path in paths:
            checked.append(str(path))
            text = path.read_text(encoding="utf-8", errors="replace")
            for name, pattern in PATTERNS.items():
                for match in pattern.finditer(text):
                    supported = (name in {"production-scale", "production Kubernetes", "production Slurm", "production disaster recovery", "zero downtime"} and "PRODUCTION" in levels) or (name in {"AMD GPU validated", "MI300", "multi-GPU"} and "REAL_HARDWARE" in levels)
                    if not supported and not _limitation_context(text, match):
                        findings.append({"file": str(path), "claim": name, "text": match.group(0)})
    return {"status": "PASS" if not findings else "FAIL", "checked_files": checked, "unsupported_claims": findings}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="evidence/infrastructure/gates.json")
    parser.add_argument("--output", default="artifacts/gate19/final-claims-scan.json")
    parser.add_argument("--root", action="append", dest="roots")
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    roots = [Path(value) for value in (args.roots or ["README.md", "docs", "release", "evidence"])]
    result = scan_claims(registry, roots)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["status"] != "PASS":
        print(json.dumps(result, indent=2))
        return 1
    print("FINAL_CLAIMS_SCAN: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
