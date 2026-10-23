"""Secret-safe PostgreSQL backup and isolated restore helper for CI drills."""
from __future__ import annotations
import argparse, os, subprocess
from pathlib import Path

def run(args: list[str]) -> None:
    subprocess.run(args, check=True, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--restore-url", required=True)
    args = parser.parse_args()
    source = os.environ.get("AGENTTRUST_POSTGRES_URL", "").strip()
    if not source:
        raise SystemExit("AGENTTRUST_POSTGRES_URL is required")
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    run(["pg_dump", "--format=custom", "--file", str(args.backup), source])
    run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--dbname", args.restore_url, str(args.backup)])
    if not args.backup.exists() or args.backup.stat().st_size == 0:
        raise SystemExit("backup artifact is empty")

if __name__ == "__main__":
    main()
