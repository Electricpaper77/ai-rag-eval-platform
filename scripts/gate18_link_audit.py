"""Audit repository-relative Markdown links without depending on external uptime."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

MARKDOWN_LINK = re.compile(r"!?(?:\[[^\]]*\])\(([^)\s]+)(?:\s+[^)]*)?\)")
ALLOWED_EXTERNAL_DOMAINS = {"github.com", "ai-agent-reliability-platform-rtcd.vercel.app", "127.0.0.1", "localhost"}


def audit_links(files: list[Path]) -> dict:
    problems: list[dict[str, str]] = []
    checked: list[str] = []
    for source in files:
        checked.append(str(source))
        text = source.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(text):
            if target.startswith("#"):
                continue
            parsed = urlparse(target)
            if parsed.scheme in {"http", "https"}:
                if not parsed.hostname or parsed.hostname not in ALLOWED_EXTERNAL_DOMAINS:
                    problems.append({"file": str(source), "target": target, "reason": "external domain is not allowlisted"})
                continue
            if parsed.scheme or target.startswith("/"):
                problems.append({"file": str(source), "target": target, "reason": "unsupported link form"})
                continue
            candidate = (source.parent / parsed.path).resolve()
            if not candidate.exists():
                problems.append({"file": str(source), "target": target, "reason": "missing repository path"})
    return {"status": "PASS" if not problems else "FAIL", "checked_files": checked, "problems": problems}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", action="append", dest="files")
    parser.add_argument("--output", default="artifacts/gate18/link-audit.json")
    args = parser.parse_args()
    files = [Path(value) for value in (args.files or ["README.md", "docs/INFRASTRUCTURE_CASE_STUDY.md", "docs/INFRASTRUCTURE_EVIDENCE_SUMMARY.md", "docs/ARCHITECTURE.md"])]
    result = audit_links(files)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["status"] != "PASS":
        print(json.dumps(result, indent=2))
        return 1
    print("LINK_AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
