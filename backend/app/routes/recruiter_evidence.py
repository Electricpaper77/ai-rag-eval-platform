"""Read-only recruiter evidence routes; missing evidence is an explicit state."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["recruiter-evidence"])
EVIDENCE_DIR = Path("artifacts/latest")


def _summary() -> dict:
    path = EVIDENCE_DIR / "summary.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No evidence pack found. Run python -m app.eval.run first.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Evidence summary is invalid JSON.") from exc


@router.get("/api/recruiter-evidence/summary")
def recruiter_evidence_summary() -> dict:
    return _summary()


@router.get("/api/recruiter-evidence/download/{filename}")
def download_evidence(filename: str) -> FileResponse:
    if filename not in {"summary.json", "results.jsonl", "run_manifest.json", "failures.jsonl"}:
        raise HTTPException(status_code=404, detail="Evidence file is not available.")
    path = EVIDENCE_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Evidence file is missing.")
    return FileResponse(path, filename=filename)


@router.get("/recruiter-evidence", response_class=HTMLResponse)
def recruiter_evidence_page() -> str:
    summary = _summary()
    badge = "Authenticated benchmark" if summary["benchmark_status"] == "authenticated" else "Mock evidence"
    cards = [("Pass rate", "evaluation_pass_rate", "Cases that met the deterministic suite's expected behavior."), ("Citation precision", "citation_precision", "Citation-required cases with all expected references."), ("Refusal accuracy", "refusal_accuracy", "Unsafe-request cases correctly declined."), ("Injection defense", "prompt_injection_defense_rate", "Prompt-injection cases correctly resisted."), ("P95 evaluator latency", "latency_p95_ms", "Local evaluator runtime; not model, GPU, or network latency."), ("Estimated cost/request", "estimated_cost_per_request_usd", "Mock estimate, not provider billing.")]
    body = "".join(f"<section><h2>{escape(label)}</h2><strong>{summary[key] * 100:.1f}%</strong><p>{escape(note)}</p></section>" if key.endswith("rate") or key.endswith("precision") or key.endswith("accuracy") else f"<section><h2>{escape(label)}</h2><strong>{summary[key]}</strong><p>{escape(note)}</p></section>" for label, key, note in cards)
    return f"""<!doctype html><title>AgentTrust IQ Evidence</title><style>body{{font:16px Arial;max-width:1100px;margin:40px auto;color:#16222e}}.badge{{display:inline-block;background:#fff1c2;padding:8px 12px;border-radius:14px;font-weight:bold}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:20px 0}}section{{border:1px solid #d7dee7;border-radius:10px;padding:16px}}h2{{font-size:15px;margin:0;color:#52606d}}strong{{font-size:28px}}p{{color:#52606d;line-height:1.4}}a{{margin-right:16px}}</style><h1>AgentTrust IQ Production Evidence</h1><p class=badge>{badge}</p><p>Latest deterministic evaluation status: <b>{escape(summary['benchmark_status'])}</b>. This pack does not claim real NVIDIA or GPU performance.</p><div class=grid>{body}</div><p><b>Provider / model:</b> {escape(summary['provider'])} / {escape(summary['model'])}<br><b>Suite hash:</b> {escape(summary['suite_sha256'])}<br><b>Git commit:</b> {escape(summary['git_commit_sha'])}</p><p><a href='/api/recruiter-evidence/download/summary.json'>Download summary.json</a><a href='/api/recruiter-evidence/download/results.jsonl'>Download results.jsonl</a></p>"""
