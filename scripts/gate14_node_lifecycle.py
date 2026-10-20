"""Evidence helpers for Gate 14 Kubernetes node lifecycle operations."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Sequence


def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be between 0 and 1")
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def summarize_traffic(records: Sequence[dict[str, Any]], started_at: str, ended_at: str) -> dict[str, Any]:
    latencies = [float(row["latency_ms"]) for row in records if row.get("ok")]
    failures = [row for row in records if not row.get("ok")]
    consecutive = 0
    maximum_consecutive = 0
    for row in records:
        if row.get("ok"):
            consecutive = 0
        else:
            consecutive += 1
            maximum_consecutive = max(maximum_consecutive, consecutive)
    failure_times = [row["timestamp"] for row in failures if row.get("timestamp")]
    disruption_seconds = 0.0
    if len(failure_times) >= 2:
        first = dt.datetime.fromisoformat(failure_times[0].replace("Z", "+00:00"))
        last = dt.datetime.fromisoformat(failure_times[-1].replace("Z", "+00:00"))
        disruption_seconds = max(0.0, (last - first).total_seconds())
    return {
        "total_requests": len(records),
        "successful_requests": len(records) - len(failures),
        "failed_requests": len(failures),
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "mean_latency_ms": mean(latencies) if latencies else None,
        "maximum_consecutive_failures": maximum_consecutive,
        "disruption_duration_seconds": disruption_seconds,
        "started_at": started_at,
        "ended_at": ended_at,
        "zero_failed_requests": not failures,
    }


def validate_placement(pods: Sequence[dict[str, Any]], expected_replicas: int = 2) -> dict[str, Any]:
    ready = [pod for pod in pods if pod.get("ready") and pod.get("phase") == "Running"]
    nodes = sorted({pod.get("node") for pod in ready if pod.get("node")})
    if len(ready) < expected_replicas:
        raise AssertionError(f"expected {expected_replicas} ready pods, got {len(ready)}")
    if len(nodes) < expected_replicas:
        raise AssertionError(f"expected replicas on {expected_replicas} nodes, got {nodes}")
    return {"ready_pods": len(ready), "nodes": nodes, "distributed": True, "pods": list(pods)}


def _kubectl(args: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(["kubectl", *args], capture_output=True, text=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def collect_placement(namespace: str, selector: str) -> dict[str, Any]:
    payload = _kubectl(["get", "pods", "-n", namespace, "-l", selector, "-o", "json"])
    pods = []
    for item in payload.get("items", []):
        statuses = {container["name"]: container for container in item.get("status", {}).get("containerStatuses", [])}
        ready = bool(statuses) and all(container.get("ready") for container in statuses.values())
        pods.append(
            {
                "name": item["metadata"]["name"],
                "uid": item["metadata"]["uid"],
                "node": item.get("spec", {}).get("nodeName"),
                "phase": item.get("status", {}).get("phase"),
                "ready": ready,
            }
        )
    return validate_placement(pods)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def run_traffic(url: str, duration: float, interval: float) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    started_at = _utc_now()
    deadline = time.monotonic() + duration
    payload = json.dumps(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Return one short maintenance status."}],
            "max_tokens": 32,
        }
    ).encode("utf-8")
    while time.monotonic() < deadline:
        started = time.perf_counter()
        status = None
        error = None
        try:
            request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                status = response.status
                response.read()
            ok = status == 200
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            ok = False
            error = str(exc)
        records.append(
            {
                "timestamp": _utc_now(),
                "ok": ok,
                "status": status,
                "error": error,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        )
        if interval:
            time.sleep(interval)
    ended_at = _utc_now()
    return {"records": records, "summary": summarize_traffic(records, started_at, ended_at)}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    placement = subparsers.add_parser("placement")
    placement.add_argument("--namespace", default="agenttrust-gate14")
    placement.add_argument("--selector", default="app=agenttrust-gate14")
    placement.add_argument("--output", type=Path, required=True)
    traffic = subparsers.add_parser("traffic")
    traffic.add_argument("--url", required=True)
    traffic.add_argument("--duration", type=float, default=60)
    traffic.add_argument("--interval", type=float, default=0.2)
    traffic.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "placement":
        _write(args.output, collect_placement(args.namespace, args.selector))
    else:
        _write(args.output, run_traffic(args.url, args.duration, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
