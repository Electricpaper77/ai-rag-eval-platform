"""Collect truthful, deterministic scheduler and tenant evidence from kubectl."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def _kubectl(*args: str) -> Any:
    result = subprocess.run(["kubectl", *args, "-o", "json"], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def _read_optional(path: str | None) -> Any:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return candidate.read_text(encoding="utf-8")


def collect(namespaces: list[str], extra: dict[str, str | None] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "nodes": _kubectl("get", "nodes"),
        "pods": _kubectl("get", "pods", "-A"),
        "priority_classes": _kubectl("get", "priorityclasses"),
        "namespaces": {},
        "events": _kubectl("get", "events", "-A", "--sort-by=.lastTimestamp"),
    }
    for namespace in namespaces:
        data["namespaces"][namespace] = {
            "quota": _kubectl("get", "resourcequota", "-n", namespace),
            "limitrange": _kubectl("get", "limitrange", "-n", namespace),
        }
    if extra:
        for name, path in extra.items():
            value = _read_optional(path)
            if value is not None:
                data[name] = value
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--namespaces", nargs="+", required=True)
    parser.add_argument("--preemption-file")
    parser.add_argument("--pending-file")
    parser.add_argument("--recovery-file")
    parser.add_argument("--tenant-isolation-file")
    args = parser.parse_args()
    extra = {
        "preemption": args.preemption_file,
        "pending": args.pending_file,
        "recovery": args.recovery_file,
        "tenant_isolation": args.tenant_isolation_file,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(collect(args.namespaces, extra), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SCHEDULER_EVIDENCE: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
