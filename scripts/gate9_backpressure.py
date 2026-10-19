"""Concurrent overflow probe that requires structured capacity rejection."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def request(url: str) -> tuple[int, str]:
    body = json.dumps({"model": "mock", "messages": [{"role": "user", "content": "overflow"}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=20)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=args.requests) as executor:
        results = list(executor.map(lambda _: request(args.url), range(args.requests)))
    rejected = [(status, body) for status, body in results if status in (429, 503)]
    assert rejected, results
    assert any('"reason_code"' in body and ("capacity_exhausted" in body or "capacity_queue_timeout" in body) for _, body in rejected), rejected
    print("BACKPRESSURE_SUMMARY " + json.dumps({"total": len(results), "rejected": len(rejected), "statuses": sorted({status for status, _ in rejected})}))
    print(rejected[0][1])


if __name__ == "__main__":
    main()
