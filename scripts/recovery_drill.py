"""Run bounded, synthetic recovery-maintenance operations.

This command is for disposable PostgreSQL/local artifacts only; it never selects
cloud storage or production databases.
"""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from saas.operations import cleanup_backup_artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--retention-seconds", type=int, default=86400)
    parser.add_argument("--execute", action="store_true", help="authorize deletion of expired disposable artifacts")
    args = parser.parse_args()
    if os.getenv("AGENTTRUST_DEPLOYMENT_POLICY", "").strip().lower() in {"production", "staging"}:
        raise SystemExit("operational recovery drill cannot run against deployment environments")
    events = cleanup_backup_artifacts(args.backup_root, max_age_seconds=args.retention_seconds, execute=args.execute)
    print(json.dumps({"schema": "agenttrust-maintenance-v1", "dry_run": not args.execute,
                      "events": events, "secrets_included": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
