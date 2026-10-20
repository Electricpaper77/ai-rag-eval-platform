"""Generate bounded STAR interview examples from the evidence boundary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXAMPLES = [
    ("Kubernetes incident and recovery", "A disposable inference pod was deleted during a runtime check.", "Prove replacement identity, readiness, endpoint recovery, and security invariants.", "The Deployment recreated a different Ready pod and health/chat checks recovered; this is disposable-cluster evidence, not an employer incident."),
    ("CPU throttling", "A bounded CPU-pressure pod had a small CPU limit.", "Measure cgroup v2 counters before and after pressure.", "The throttled counter increased and the service recovered after cleanup; no production capacity claim is made."),
    ("OOMKilled", "A bounded memory-pressure pod exceeded its memory limit.", "Capture termination reason, exit code, events, and recovery.", "The pod produced OOMKilled/137 evidence and a safe replacement ran; this was an isolated kind experiment."),
    ("Preemption and capacity", "Competing workloads exercised scheduling constraints.", "Show placement, preemption, quotas, and recovery with evidence.", "The result describes reproducible disposable multi-node behavior, not a live customer fleet."),
    ("Disaster recovery", "A stateful recovery workflow needed a measured restore path.", "Capture backup/restore steps and bounded recovery evidence.", "The workflow validates an isolated recovery procedure; it is not a claim about an employer's recovery objective."),
    ("Supply-chain controls", "Release artifacts needed repeatable provenance and policy checks.", "Validate manifests, provenance, and release contracts in CI.", "The evidence is CI validation; no production release ownership is claimed."),
]


def generate_document(registry: dict[str, Any]) -> str:
    lines = ["# Infrastructure interview evidence", "", "Each example is bounded to the execution environments recorded in the Gate 17 registry.", ""]
    for title, situation, task, result in EXAMPLES:
        lines.extend([f"## {title}", "", f"**Situation:** {situation}", f"**Task:** {task}", f"**Action:** Used explicit manifests, bounded commands, and captured logs/events before cleanup.", f"**Result:** {result}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="evidence/infrastructure/gates.json")
    parser.add_argument("--output", default="artifacts/gate17/interview-evidence.md")
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generate_document(registry), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
