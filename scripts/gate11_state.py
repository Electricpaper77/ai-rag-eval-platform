"""Small deterministic state lifecycle helper used by Gate 11 runtime tests."""

from __future__ import annotations

import argparse
import json

from backend.app.recovery.service import RecoveryService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=("seed", "append", "corrupt", "status"), required=True)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--start", type=int, default=1)
    args = parser.parse_args()
    service = RecoveryService()
    if args.action == "seed":
        result = service.seed(args.count, args.start)
    elif args.action == "append":
        result = service.append(args.count)
    elif args.action == "corrupt":
        result = {"corrupted": str(service.corrupt())}
    else:
        result = service.status()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
