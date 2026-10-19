from __future__ import annotations

import argparse
import json
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--action", choices=("inject", "recover"), required=True)
    parser.add_argument("--fault-type")
    parser.add_argument("--duration", type=float, default=15.0)
    args = parser.parse_args()
    payload = {} if args.action == "recover" else {"fault_type": args.fault_type, "duration_seconds": args.duration}
    request = urllib.request.Request(
        f"{args.url.rstrip('/')}/platform/resilience/{args.action}",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.read().decode(), flush=True)


if __name__ == "__main__":
    main()
