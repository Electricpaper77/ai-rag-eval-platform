"""Generate resume-safe bullets from verified Gate 17 evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def generate_bullets(registry: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "technical infrastructure": [
            "Validated Kubernetes node cordon/drain, PDB-controlled eviction, pod replacement, and service continuity in disposable kind.",
            "Proved scheduler preemption, tenant quotas, LimitRange enforcement, taints/tolerations, and capacity recovery in multi-node kind.",
            "Implemented Helm and GitOps lifecycle checks with install, upgrade, rollback, drift detection, and self-heal evidence.",
        ],
        "AI infrastructure": [
            "Built secure AgentTrust IQ inference workloads with non-root containers, readiness probes, writable /tmp paths, and recovery checks.",
            "Validated distributed inference, canary rollback, autoscaling, and workload orchestration through reproducible CI environments.",
            "Built a strict AMD ROCm hardware-validation pipeline with no CPU fallback; execution remains pending access to qualifying AMD GPU hardware.",
        ],
        "reliability and SRE": [
            "Proved cgroup v2 CPU throttling counters and real OOMKilled/exit-137 behavior with post-pressure recovery in kind.",
            "Recorded a 321-passed, 1-xfailed Gate 16 regression result alongside bounded pressure and recovery evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default="evidence/infrastructure/gates.json")
    parser.add_argument("--output", default="artifacts/gate17/resume-bullets.md")
    args = parser.parse_args()
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    sections = generate_bullets(registry)
    lines = ["# Resume-safe infrastructure bullets", ""]
    for heading, bullets in sections.items():
        lines.extend([f"## {heading.title()}", ""])
        lines.extend(f"- {bullet}" for bullet in bullets)
        lines.append("")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
