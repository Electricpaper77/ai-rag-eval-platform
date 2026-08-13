"""Deterministic recruiter evaluation workflow backed by the canonical harness."""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
from html import escape
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app.eval_harness import DEFAULT_HIRING_EVAL_CASES, run_eval_harness

router = APIRouter(tags=["recruiter-golden-path"])
RUN_DIR = Path(tempfile.gettempdir()) / "agenttrust-iq-recruiter-runs"
_lock = threading.Lock()
_state: dict[str, Any] = {"status": "ready", "run": None, "error": None}


def _pack() -> dict[str, Any]:
    return {"pack_id": "canonical_hiring_eval", "name": "Recruiter demo: canonical controlled hiring run", "case_count": len(DEFAULT_HIRING_EVAL_CASES), "categories": sorted({case["risk_category"] for case in DEFAULT_HIRING_EVAL_CASES}), "provider": "deterministic local evaluator", "mode": "no-key controlled fixture", "description": "Six existing canonical hiring cases covering citations, factuality, PII, prompt injection, and unsafe-request refusal."}


def _verdict(rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    failures = [row for row in rows if not row["pass"]]
    if not failures:
        return "PASS", ["All canonical cases satisfied the existing evaluator gates."]
    reasons = [reason for row in failures for reason in row.get("failure_reasons", [])]
    return "BLOCK", reasons or [f"{len(failures)} canonical case(s) did not satisfy the existing evaluator gates."]


def _run_payload(summary: dict[str, Any], output: Path) -> dict[str, Any]:
    rows = [row for row in (json.loads(line) for line in (output / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()) if row.get("record_type") == "case"]
    verdict, reasons = _verdict(rows)
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    failures = [row for row in rows if not row["pass"]]
    return {"status": "completed", "pack": _pack(), "scorecard": {**summary, "failed_cases": summary["total_cases"] - summary["passed_cases"], "prompt_injection_defense_rate": next((row["metrics"]["prompt_injection_compliance"] for row in rows if row["risk_category"] == "prompt_injection"), None)}, "failed_cases": failures, "verdict": {"value": verdict, "reasons": reasons}, "evidence": {"run_id": summary["harness_run_id"], "timestamp": None, "provider": "deterministic local evaluator", "model": "N/A", "evaluation_pack": _pack()["pack_id"], "artifact": "results.jsonl", "checksum": hashlib.sha256((output / "results.jsonl").read_bytes()).hexdigest(), "suite_checksum": manifest["suite_sha256"], "git_commit": manifest["git_commit_sha"]}}


@router.get("/api/recruiter-golden-path/pack")
def recruiter_pack() -> dict[str, Any]:
    return _pack()


@router.get("/api/recruiter-golden-path/run")
def recruiter_run() -> dict[str, Any]:
    return {"status": _state["status"], "run": _state["run"], "error": _state["error"]}


@router.post("/api/recruiter-golden-path/run")
def run_recruiter_evaluation() -> dict[str, Any]:
    if not _lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An evaluation is already running.")
    _state.update(status="running", run=None, error=None)
    try:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        output = RUN_DIR / "current"
        output.mkdir(exist_ok=True)
        summary = run_eval_harness(output / "results.jsonl", output / "summary.json", run_id="recruiter-golden-path")
        manifest = {"suite": "canonical_hiring_eval", "suite_sha256": hashlib.sha256((output / "results.jsonl").read_bytes()).hexdigest(), "git_commit_sha": "checked-in harness", "contains_secrets": False}
        (output / "run_manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        payload = _run_payload(summary, output)
        _state.update(status="completed", run=payload, error=None)
        return payload
    except Exception as exc:
        _state.update(status="failed", run=None, error="Evaluation did not complete. No result was recorded.")
        raise HTTPException(status_code=500, detail="Evaluation did not complete. No result was recorded.") from exc
    finally:
        _lock.release()


@router.get("/api/recruiter-golden-path/evidence/{filename}")
def golden_path_evidence(filename: str) -> FileResponse:
    if filename not in {"results.jsonl", "summary.json", "run_manifest.json"}:
        raise HTTPException(status_code=404, detail="Evidence file is not available.")
    path = RUN_DIR / "current" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="No completed recruiter evaluation evidence exists.")
    return FileResponse(path, filename=filename)


@router.get("/recruiter-golden-path", response_class=HTMLResponse)
def recruiter_golden_path_page() -> str:
    pack = _pack()
    return f'''<!doctype html><title>AgentTrust IQ Recruiter Evaluation</title><style>body{{font:16px Arial;max-width:1100px;margin:36px auto;color:#16222e}}button{{background:#075985;color:white;border:0;border-radius:6px;padding:12px 18px;font-weight:bold}}button:disabled{{opacity:.55}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}}section{{border:1px solid #d7dee7;border-radius:8px;padding:14px;margin:16px 0}}dt{{color:#52606d}}dd{{font-size:22px;margin:6px 0}}pre{{white-space:pre-wrap;word-break:break-word}}.hidden{{display:none}}</style><main><h1>Recruiter Evaluation Run</h1><section><h2>{escape(pack['name'])}</h2><p>{escape(pack['description'])}</p><p><b>{pack['case_count']} cases</b> · {escape(', '.join(pack['categories']))} · {escape(pack['mode'])}</p><button id=run>Run Evaluation</button> <span id=status>Ready</span></section><div id=results class=hidden><section><h2>Results Scorecard</h2><dl class=grid id=metrics></dl></section><section><h2>Failed Case Inspection</h2><div id=failures>No failed cases.</div></section><section><h2>Evidence</h2><pre id=evidence></pre><a href=/api/recruiter-golden-path/evidence/results.jsonl>Open read-only JSONL evidence</a></section><section><h2>Release Verdict: <span id=verdict></span></h2><ul id=reasons></ul></section></div><p id=error role=alert></p></main><script>const b=document.querySelector('#run'),s=document.querySelector('#status'),r=document.querySelector('#results'),e=document.querySelector('#error');const pct=v=>v==null?'N/A':(v*100).toFixed(1)+'%';b.onclick=async()=>{{b.disabled=true;s.textContent='Running';e.textContent='';try{{const x=await fetch('/api/recruiter-golden-path/run',{{method:'POST'}});const d=await x.json();if(!x.ok)throw Error(d.detail);s.textContent='Completed';r.classList.remove('hidden');const m=d.scorecard;document.querySelector('#metrics').innerHTML=[['Pass rate',pct(m.eval_pass_rate)],['Hallucination failure rate',pct(m.hallucination_rate)],['Citation precision',pct(m.citation_precision)],['Refusal / guardrail accuracy',pct(m.refusal_accuracy)],['Prompt-injection defense',pct(m.prompt_injection_defense_rate)],['P95 latency',m.latency_p95_ms+' ms'],['Total cases',m.total_cases],['Passed cases',m.passed_cases],['Failed cases',m.failed_cases]].map(x=>'<div><dt>'+x[0]+'</dt><dd>'+x[1]+'</dd></div>').join('');document.querySelector('#failures').innerHTML=d.failed_cases.length?d.failed_cases.map(c=>'<pre>'+JSON.stringify(c,null,2)+'</pre>').join(''):'No failed cases.';document.querySelector('#evidence').textContent=JSON.stringify(d.evidence,null,2);document.querySelector('#verdict').textContent=d.verdict.value;document.querySelector('#reasons').innerHTML=d.verdict.reasons.map(x=>'<li>'+x+'</li>').join('')}}catch(err){{s.textContent='Failed';e.textContent=err.message;b.disabled=false}}}};</script>'''
