"""Bounded concurrent HTTP load for disposable Gate 9 validation."""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def one(url: str, timeout: float) -> tuple[int, float, str]:
    started = time.perf_counter()
    payload = json.dumps({"model": "mock", "messages": [{"role": "user", "content": "gate9 capacity"}]}).encode()
    request = urllib.request.Request(url, data=payload, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
            return response.status, (time.perf_counter() - started) * 1000.0, ""
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return exc.code, (time.perf_counter() - started) * 1000.0, body
    except Exception as exc:
        return 0, (time.perf_counter() - started) * 1000.0, type(exc).__name__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    deadline = time.monotonic() + args.duration
    rows: list[tuple[int, float, str]] = []
    lock = threading.Lock()

    def worker() -> None:
        while time.monotonic() < deadline:
            row = one(args.url, args.timeout)
            with lock:
                rows.append(row)

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = [executor.submit(worker) for _ in range(max(1, args.concurrency))]
        for future in futures:
            future.result()
    counts: dict[str, int] = {}
    for status, _, _ in rows:
        counts[str(status)] = counts.get(str(status), 0) + 1
    summary = {"requests": len(rows), "status_counts": counts, "successes": counts.get("200", 0), "errors": len(rows) - counts.get("200", 0)}
    print("LOAD_SUMMARY " + json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
