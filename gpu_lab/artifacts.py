from __future__ import annotations
import csv, json, os, tempfile
from pathlib import Path

def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True); temp = handle.name
    os.replace(temp, path)

def write_run(root: Path, manifest: dict, records: list[dict], summary: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(root / "run-manifest.json", manifest); atomic_json(root / "benchmark-summary.json", summary)
    atomic_json(root / "quality-summary.json", {"status": "not_measured"})
    for name, rows in (("requests.jsonl", records), ("telemetry.jsonl", [])):
        with (root / name).open("w", encoding="utf-8") as f:
            for row in rows: f.write(json.dumps(row, sort_keys=True) + "\n")
    with (root / "failure-analysis.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["request_id", "failure_type", "error"]); writer.writeheader()
        for r in records:
            if r.get("error"): writer.writerow({"request_id": r["request_id"], "failure_type": r.get("failure_type"), "error": r["error"]})
    return root
