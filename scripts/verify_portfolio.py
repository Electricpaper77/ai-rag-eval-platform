"""Fast recruiter-facing release-candidate validation."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.gate17_claims_audit import audit_claims
from scripts.gate17_evidence_integrity import validate_registry
from scripts.gate18_link_audit import audit_links

REQUIRED_PATHS = [
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/INFRASTRUCTURE_CASE_STUDY.md",
    "docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md",
    "evidence/infrastructure/gates.json",
    "evidence/project-capabilities.json",
    "release/agenttrust-iq-release.json",
    "scripts/gate17_claims_audit.py",
    "scripts/gate18_link_audit.py",
    "tests/test_gate18_portfolio_release.py",
]
REQUIRED_WORKFLOWS = [".github/workflows/gate17-infrastructure-evidence.yml", ".github/workflows/gate18-portfolio-release.yml"]


def verify() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for relative in REQUIRED_PATHS + REQUIRED_WORKFLOWS:
        if not (ROOT / relative).exists():
            errors.append(f"missing required path: {relative}")
    try:
        registry = json.loads((ROOT / "evidence/infrastructure/gates.json").read_text(encoding="utf-8"))
        if validate_registry(registry):
            errors.append("Gate 17 registry integrity failed")
        gate13 = next(entry for entry in registry["gates"] if entry["gate"] == "13")
        if gate13["status"] != "BLOCKED" or gate13["evidence_level"] != "BLOCKED":
            errors.append("Gate 13 is not explicitly BLOCKED")
        capabilities = json.loads((ROOT / "evidence/project-capabilities.json").read_text(encoding="utf-8"))
        if capabilities.get("project") != "AgentTrust IQ" or capabilities.get("release_candidate") is not True:
            errors.append("capability manifest identity/schema failed")
        if capabilities.get("blocked") != ["13"]:
            errors.append("capability manifest must identify Gate 13 as blocked")
        release = json.loads((ROOT / "release/agenttrust-iq-release.json").read_text(encoding="utf-8"))
        if release.get("name") != "AgentTrust IQ" or release.get("baseline_sha") != "a79c62b8576a565ee7c11c197b072dfac8f5eff8":
            errors.append("release manifest identity failed")
        if release.get("blocked_items") == []:
            errors.append("release manifest must retain blocked items")
        claim_files = [ROOT / name for name in ["README.md", "docs/INFRASTRUCTURE_CASE_STUDY.md", "docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md", "docs/ARCHITECTURE.md"]]
        if audit_claims(registry, claim_files)["status"] != "PASS":
            errors.append("claim consistency failed")
        if audit_links(claim_files)["status"] != "PASS":
            errors.append("repository link audit failed")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for heading in ("What it does", "Key validated capabilities", "Evidence", "Architecture", "Run locally", "Scope / limitations"):
            if f"## {heading}" not in readme:
                errors.append(f"README missing section: {heading}")
        if re.search(r"production\s+(?:kubernetes|scale|gpu|slurm)|zero[- ]downtime|mi300|multi[- ]gpu", readme, re.I):
            errors.append("README contains an unsupported claim")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"portfolio parse failure: {exc}")
    return not errors, errors


def main() -> int:
    ok, errors = verify()
    if not ok:
        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        return 1
    print("PORTFOLIO_VERIFICATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
