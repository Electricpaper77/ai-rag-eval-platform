"""Validate the Gate 17 machine-readable evidence registry."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_GATES = {"1", "2", "3A", "3B", "3C", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16"}
LEVELS = {"STATIC", "CI_RUNTIME", "DISPOSABLE_CLUSTER_RUNTIME", "REAL_HARDWARE", "PRODUCTION", "BLOCKED"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if registry.get("repository") != "Electricpaper77/ai-rag-eval-platform":
        errors.append("repository identity is incorrect")
    baseline = registry.get("baseline_sha")
    if not isinstance(baseline, str) or not SHA_RE.fullmatch(baseline):
        errors.append("baseline_sha must be a 40-character SHA")
    gates = registry.get("gates")
    if not isinstance(gates, list):
        return errors + ["gates must be a list"]
    ids = [entry.get("gate") for entry in gates if isinstance(entry, dict)]
    if len(ids) != len(set(ids)):
        errors.append("gate identifiers must be unique")
    if set(ids) != REQUIRED_GATES:
        errors.append(f"required gate set mismatch: {sorted(set(ids) ^ REQUIRED_GATES)}")
    for entry in gates:
        if not isinstance(entry, dict):
            errors.append("every gate entry must be an object")
            continue
        gate = entry.get("gate")
        if entry.get("status") not in {"PASS", "BLOCKED"}:
            errors.append(f"{gate}: invalid status")
        level = entry.get("evidence_level")
        if level not in LEVELS:
            errors.append(f"{gate}: invalid evidence level")
        sha = entry.get("feature_sha")
        if sha is not None and (not isinstance(sha, str) or not SHA_RE.fullmatch(sha)):
            errors.append(f"{gate}: feature_sha must be null or a 40-character SHA")
        for key in ("workflow_run_id", "job_id", "artifact_id"):
            value = entry.get(key)
            if value is not None and (not isinstance(value, int) or value <= 0):
                errors.append(f"{gate}: {key} must be a positive integer or null")
        digest = entry.get("artifact_digest")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
            errors.append(f"{gate}: artifact_digest must be sha256:<64 hex> or null")
        if gate == "13":
            if entry.get("status") != "BLOCKED" or level != "BLOCKED":
                errors.append("Gate 13 must remain BLOCKED")
            if entry.get("executed_evidence"):
                errors.append("Gate 13 cannot contain executed evidence")
        if entry.get("status") == "BLOCKED" and level != "BLOCKED":
            errors.append(f"{gate}: blocked status requires BLOCKED evidence level")
        if level == "REAL_HARDWARE":
            text = " ".join(map(str, entry.get("executed_evidence", []))).lower()
            if not any(token in text for token in ("gpu", "hardware", "rocm", "hip")):
                errors.append(f"{gate}: REAL_HARDWARE requires explicit hardware evidence")
        if level == "PRODUCTION":
            errors.append(f"{gate}: PRODUCTION evidence requires separately reviewed production proof")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="evidence/infrastructure/gates.json")
    parser.add_argument("--output", default="artifacts/gate17/evidence-integrity.json")
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    errors = validate_registry(registry)
    result = {"status": "PASS" if not errors else "FAIL", "errors": errors, "registry": args.registry}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if errors:
        print(json.dumps(result, indent=2))
        return 1
    print("EVIDENCE_INTEGRITY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
