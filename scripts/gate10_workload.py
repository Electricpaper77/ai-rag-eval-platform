"""Bounded deterministic HTTP workload and SLO summary for Gate 10."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request


def run(url: str, requests: int) -> dict[str, object]:
    rows: list[tuple[int, float, str]] = []
    for _ in range(max(1, requests)):
        started = time.perf_counter()
        body = json.dumps({"model": "mock", "messages": [{"role": "user", "content": "gate10 resilience"}]}).encode()
        request = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5.0) as response:
                response.read()
                rows.append((response.status, (time.perf_counter() - started) * 1000.0, ""))
        except urllib.error.HTTPError as exc:
            rows.append((exc.code, (time.perf_counter() - started) * 1000.0, exc.read().decode(errors="replace")))
        except Exception as exc:
            rows.append((0, (time.perf_counter() - started) * 1000.0, type(exc).__name__))
    latencies = sorted(row[1] for row in rows)
    success = sum(1 for status, _, _ in rows if 200 <= status < 300)
    failures = len(rows) - success
    p95_index = min(len(latencies) - 1, max(0, int(len(latencies) * 0.95) - 1))
    return {
        "total_requests": len(rows),
        "successes": success,
        "failed_requests": failures,
        "availability": round(success / len(rows), 6) if rows else 0.0,
        "error_rate": round(failures / len(rows), 6) if rows else 0.0,
        "p50_ms": round(statistics.median(latencies), 3) if latencies else 0.0,
        "p95_ms": round(latencies[p95_index], 3) if latencies else 0.0,
        "status_counts": {str(status): sum(1 for item in rows if item[0] == status) for status in sorted({item[0] for item in rows})},
        "errors": [message for _, _, message in rows if message][:10],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=20)
    args = parser.parse_args()
    summary = run(args.url, args.requests)
    print("WORKLOAD_SUMMARY " + json.dumps(summary, sort_keys=True), flush=True)
    if summary["successes"] == 0 and summary["failed_requests"] == 0:
        raise SystemExit("no requests executed")


if __name__ == "__main__":
    main()
