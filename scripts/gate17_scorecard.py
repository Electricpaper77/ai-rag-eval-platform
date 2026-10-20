"""Generate a non-subjective Gate 17 infrastructure scorecard."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_scorecard(registry: dict[str, Any], claims_audit: str = "PASS") -> dict[str, Any]:
    gates = registry["gates"]
    completed = [entry["gate"] for entry in gates if entry["status"] == "PASS"]
    blocked = [entry["gate"] for entry in gates if entry["status"] == "BLOCKED"]
    runtime_levels = {"CI_RUNTIME", "DISPOSABLE_CLUSTER_RUNTIME", "REAL_HARDWARE", "PRODUCTION"}
    return {
        "completed_gates": completed,
        "blocked_gates": blocked,
        "runtime_validated_gates": [entry["gate"] for entry in gates if entry["evidence_level"] in runtime_levels],
        "real_hardware_validated_gates": [entry["gate"] for entry in gates if entry["evidence_level"] == "REAL_HARDWARE"],
        "production_validated_gates": [entry["gate"] for entry in gates if entry["evidence_level"] == "PRODUCTION"],
        "latest_main_sha": registry["baseline_sha"],
        "claims_audit": claims_audit,
        "limitations": [entry.get("limitations", []) for entry in gates if entry.get("limitations")],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="evidence/infrastructure/gates.json")
    parser.add_argument("--claims-audit", default="artifacts/gate17/claims-audit.json")
    parser.add_argument("--output", default="artifacts/gate17/infrastructure-scorecard.json")
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    audit = json.loads(Path(args.claims_audit).read_text(encoding="utf-8"))
    result = build_scorecard(registry, audit.get("status", "FAIL"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
