"""Parse real Linux/Kubernetes resource evidence for Gate 16."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence


def parse_cgroup_version(stat_filesystem: str) -> str:
    value = stat_filesystem.strip().lower()
    if "cgroup2" in value:
        return "v2"
    if "cgroup" in value:
        return "v1"
    return "unknown"


def parse_cpu_stat(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            result[parts[0]] = int(parts[1])
    return result


def cpu_throttle_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    keys = {"nr_periods", "nr_throttled", "throttled_usec", "throttled_time"}
    return {key: max(0, after.get(key, 0) - before.get(key, 0)) for key in keys if key in before or key in after}


def parse_oom_status(payload: dict[str, Any]) -> dict[str, Any]:
    statuses = payload.get("status", {}).get("containerStatuses", [])
    for status in statuses:
        terminated = status.get("state", {}).get("terminated") or status.get("lastState", {}).get("terminated")
        if terminated:
            return {
                "reason": terminated.get("reason"),
                "exit_code": terminated.get("exitCode"),
                "oom_killed": terminated.get("reason") == "OOMKilled" and terminated.get("exitCode") == 137,
            }
    return {"reason": None, "exit_code": None, "oom_killed": False}


def classify_failure(
    pod: dict[str, Any],
    events: str = "",
    throttle_delta: dict[str, int] | None = None,
) -> str:
    oom = parse_oom_status(pod)
    if oom["oom_killed"]:
        return "OOMKilled"
    phase = pod.get("status", {}).get("phase")
    text = events.lower()
    if phase == "Pending" or "unschedulable" in text or "insufficient cpu" in text:
        return "Unschedulable"
    if throttle_delta and throttle_delta.get("nr_throttled", 0) > 0:
        return "CPUThrottled"
    if phase == "Running":
        return "healthy"
    reasons = [str(item.get("reason", "")) for item in pod.get("status", {}).get("containerStatuses", [])]
    if "CrashLoopBackOff" in reasons or "CrashLoopBackOff" in text:
        return "CrashLoopBackOff"
    return "unknown"


def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def summarize_traffic(records: Sequence[dict[str, Any]], started_at: str, ended_at: str) -> dict[str, Any]:
    successes = [row for row in records if row.get("ok")]
    failures = [row for row in records if not row.get("ok")]
    latencies = [float(row["latency_ms"]) for row in successes]
    current = maximum = 0
    for row in records:
        if row.get("ok"):
            current = 0
        else:
            current += 1
            maximum = max(maximum, current)
    elapsed = max(0.001, (dt.datetime.fromisoformat(ended_at.replace("Z", "+00:00")) - dt.datetime.fromisoformat(started_at.replace("Z", "+00:00"))).total_seconds())
    return {
        "total_requests": len(records),
        "successful_requests": len(successes),
        "failed_requests": len(failures),
        "requests_per_second": round(len(records) / elapsed, 3),
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "mean_latency_ms": round(mean(latencies), 3) if latencies else None,
        "maximum_consecutive_failures": maximum,
        "started_at": started_at,
        "ended_at": ended_at,
    }


def run_traffic(url: str, duration: float, interval: float) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    started = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    deadline = time.monotonic() + duration
    body = json.dumps({"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Return one short pressure-test status."}], "max_tokens": 16}).encode()
    while time.monotonic() < deadline:
        begin = time.perf_counter()
        status = None
        error = None
        try:
            request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                status = response.status
                response.read()
            ok = status == 200
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            ok = False
            error = str(exc)
        records.append({"timestamp": time.time(), "ok": ok, "status": status, "error": error, "latency_ms": (time.perf_counter() - begin) * 1000})
        if interval:
            time.sleep(interval)
    ended = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return {"records": records, "summary": summarize_traffic(records, started, ended)}


def _read_json(path: str | None) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}


def build_diagnostics(
    oom_path: str | None,
    pending_path: str | None,
    events_path: str | None,
    cpu_before_path: str | None,
    cpu_after_path: str | None,
) -> dict[str, Any]:
    oom = _read_json(oom_path)
    pending = Path(pending_path).read_text(encoding="utf-8") if pending_path else ""
    events = Path(events_path).read_text(encoding="utf-8") if events_path else ""
    before = parse_cpu_stat(Path(cpu_before_path).read_text(encoding="utf-8")) if cpu_before_path else {}
    after = parse_cpu_stat(Path(cpu_after_path).read_text(encoding="utf-8")) if cpu_after_path else {}
    delta = cpu_throttle_delta(before, after) if before or after else {}
    return {
        "cgroup": {"cpu_before": before, "cpu_after": after, "cpu_delta": delta},
        "failures": {
            "oom": parse_oom_status(oom),
            "scheduler": "Unschedulable" if re.search(r"Pending|Insufficient cpu|did not match", pending + events, re.I) else "unknown",
            "cpu": "CPUThrottled" if delta.get("nr_throttled", 0) > 0 else "unknown",
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    traffic = sub.add_parser("traffic")
    traffic.add_argument("--url", required=True)
    traffic.add_argument("--duration", type=float, default=15)
    traffic.add_argument("--interval", type=float, default=0.2)
    traffic.add_argument("--output", type=Path, required=True)
    report = sub.add_parser("report")
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--oom-path")
    report.add_argument("--pending-path")
    report.add_argument("--events-path")
    report.add_argument("--cpu-before-path")
    report.add_argument("--cpu-after-path")
    args = parser.parse_args(argv)
    if args.command == "traffic":
        payload = run_traffic(args.url, args.duration, args.interval)
    else:
        payload = build_diagnostics(args.oom_path, args.pending_path, args.events_path, args.cpu_before_path, args.cpu_after_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
