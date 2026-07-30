"""Build or validate the checked-in recruiter evidence summary."""
from __future__ import annotations

import argparse, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/artifacts/evidence_manifest.json"
SUMMARY = ROOT / "docs/artifacts/evidence_summary.json"
MARKDOWN = ROOT / "docs/artifacts/EVIDENCE_SUMMARY.md"

def records(path: Path) -> int:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    case_rows = [row for row in rows if row.get("record_type") == "case"]
    return len(case_rows) if case_rows else len(rows)

def checksum(path: Path) -> str:
    """Hash text artifacts consistently across Git's CRLF/LF checkout modes."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

def validate(data: dict) -> None:
    required = {"suite_id", "display_name", "purpose", "evidence_type", "case_count", "passed_count", "failed_count", "metrics", "latency_scope", "provider_scope", "artifact_paths", "generating_command", "production_claim_allowed"}
    for suite in data["suites"]:
        missing = required - set(suite)
        if missing: raise ValueError(f"{suite.get('suite_id')}: missing {sorted(missing)}")
        if suite["evidence_type"] in {"mock", "simulated", "not_run"} and suite["production_claim_allowed"]: raise ValueError(f"{suite['suite_id']}: unsupported production claim")
        if suite["evidence_type"] == "not_run" and suite["metrics"]: raise ValueError(f"{suite['suite_id']}: not_run may not contain metrics")
        for artifact in suite["artifact_paths"]:
            path = ROOT / artifact
            if not path.exists(): raise ValueError(f"{suite['suite_id']}: missing artifact {artifact}")
        primary = ROOT / suite["artifact_paths"][0]
        if suite.get("sha256") and checksum(primary) != suite["sha256"]: raise ValueError(f"{suite['suite_id']}: checksum mismatch")
        if primary.suffix == ".jsonl" and records(primary) != suite["case_count"]: raise ValueError(f"{suite['suite_id']}: JSONL case count mismatch")

def build(data: dict) -> tuple[dict, str]:
    canonical = next(s for s in data["suites"] if s["suite_id"] == data["homepage_canonical_suite_id"])
    summary = {"canonical_suite_id": canonical["suite_id"], "canonical_metrics": canonical["metrics"], "suites": data["suites"]}
    lines = ["# Evidence Summary", "", "Homepage headline metrics use only **Canonical controlled hiring run** (6 deterministic cases). Other suites are coverage or fixture evidence and are not combined into a benchmark.", ""]
    for s in data["suites"]:
        lines += [f"## {s['display_name']}", f"- Type: `{s['evidence_type']}`; cases: {s['case_count']}; passed: {s['passed_count']}; failed: {s['failed_count']}", f"- Execution: {s['provider_scope']}. {s['latency_scope']}", f"- Artifacts: {', '.join('`' + p + '`' for p in s['artifact_paths'])}", f"- Reproduce: `{s['generating_command']}`", ""]
    return summary, "\n".join(lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    data = json.loads(MANIFEST.read_text(encoding="utf-8")); validate(data); summary, markdown = build(data)
    if args.check:
        if not SUMMARY.exists() or not MARKDOWN.exists() or json.loads(SUMMARY.read_text()) != summary or MARKDOWN.read_text(encoding="utf-8") != markdown: raise SystemExit("evidence summary is stale; run python scripts/build_evidence_summary.py")
    else:
        SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8"); MARKDOWN.write_text(markdown, encoding="utf-8")
