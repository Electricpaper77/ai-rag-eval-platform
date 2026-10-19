from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--query")
    parser.add_argument("--alerts", action="store_true")
    args = parser.parse_args()
    if args.alerts:
        url = f"{args.base_url.rstrip('/')}/api/v1/alerts"
    else:
        url = f"{args.base_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': args.query})}"
    with urllib.request.urlopen(url, timeout=10) as response:
        print(response.read().decode(), flush=True)


if __name__ == "__main__":
    main()
