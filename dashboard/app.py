from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

from scripts.build_eval_dashboard import ARTIFACTS_DIR, summarize_runs

app = FastAPI(title="LLM Eval Dashboard")
SUMMARY_PATH = ARTIFACTS_DIR / "eval_dashboard_summary.json"


def _read_or_build_summary() -> dict:
    if SUMMARY_PATH.exists():
        with SUMMARY_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return summarize_runs(Path("artifacts/proof"))


@app.get("/dashboard/summary")
def get_dashboard_summary() -> dict:
    return _read_or_build_summary()


@app.get("/dashboard/run/{run_id}")
def get_dashboard_run(run_id: str) -> dict:
    payload = _read_or_build_summary()
    for run in payload.get("runs", []):
        if run.get("run_id") == run_id:
            return run
    raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
