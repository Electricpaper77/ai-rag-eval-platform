"""Validate final release metadata and its evidence boundary."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.gate17_claims_audit import audit_claims
from scripts.gate17_evidence_integrity import validate_registry
from scripts.gate18_link_audit import audit_links
from scripts.gate19_claim_scan import scan_claims

def audit_release(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    required = [
        "VERSION", "evidence/infrastructure/gates.json", "evidence/project-capabilities.json",
        "release/agenttrust-iq-release.json", "docs/ARCHITECTURE.md", "docs/INFRASTRUCTURE_CASE_STUDY.md",
        "docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md", "docs/RELEASE_NOTES_V1.md", "docs/PROJECT_STATUS.md",
    ]
    for relative in required:
        if not (root / relative).exists():
            errors.append(f"missing required path: {relative}")
    try:
        if (root / "VERSION").read_text(encoding="utf-8").strip() != "1.0.0":
            errors.append("VERSION must be 1.0.0")
        registry = json.loads((root / "evidence/infrastructure/gates.json").read_text(encoding="utf-8"))
        errors.extend(validate_registry(registry))
        gate13 = next(entry for entry in registry["gates"] if entry["gate"] == "13")
        if gate13["status"] != "BLOCKED" or gate13["evidence_level"] != "BLOCKED" or gate13["executed_evidence"]:
            errors.append("Gate 13 must remain blocked without executed evidence")
        capabilities = json.loads((root / "evidence/project-capabilities.json").read_text(encoding="utf-8"))
        if capabilities.get("blocked") != ["13"]:
            errors.append("capability manifest must block Gate 13")
        release = json.loads((root / "release/agenttrust-iq-release.json").read_text(encoding="utf-8"))
        for key in ("evidence_registry", "case_study", "architecture"):
            if not (root / release[key]).exists():
                errors.append(f"release manifest reference missing: {release[key]}")
        if any(entry.get("evidence_level") == "REAL_HARDWARE" for entry in registry["gates"]):
            errors.append("REAL_HARDWARE evidence is not supported by the current release proof")
        if any(entry.get("evidence_level") == "PRODUCTION" for entry in registry["gates"]):
            errors.append("PRODUCTION evidence is not supported by the current release proof")
        docs = [root / name for name in ("README.md", "docs/ARCHITECTURE.md", "docs/INFRASTRUCTURE_CASE_STUDY.md", "docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md", "docs/RELEASE_NOTES_V1.md", "docs/PROJECT_STATUS.md")]
        if audit_claims(registry, docs)["status"] != "PASS":
            errors.append("Gate 17 claims audit failed for release documents")
        if scan_claims(registry, [root / "README.md", root / "docs", root / "release", root / "evidence"])["status"] != "PASS":
            errors.append("final claims scan failed")
        if audit_links([root / "README.md", root / "docs/ARCHITECTURE.md", root / "docs/INFRASTRUCTURE_CASE_STUDY.md", root / "docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md", root / "docs/RELEASE_NOTES_V1.md"])["status"] != "PASS":
            errors.append("internal documentation references failed")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"release audit parse failure: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/gate19/final-release-audit.json")
    args = parser.parse_args()
    errors = audit_release()
    result = {"status": "PASS" if not errors else "FAIL", "errors": errors}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if errors:
        print(json.dumps(result, indent=2))
        return 1
    print("FINAL_RELEASE_AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
