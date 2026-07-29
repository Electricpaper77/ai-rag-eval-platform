from __future__ import annotations
import json, os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from gpu_lab.telemetry import AmdSmiTelemetry

router = APIRouter(tags=["gpu-lab"])
def root(): return Path(os.getenv("AGENTTRUST_ARTIFACT_DIR", "artifacts")) / "gpu-lab"
def runs():
    return sorted((p for p in root().glob("*/run-manifest.json")), reverse=True) if root().exists() else []
def load(path): return json.loads(path.read_text(encoding="utf-8"))

@router.get("/api/gpu-lab/runs")
def list_runs(): return [load(p) for p in runs()]
@router.get("/api/gpu-lab/summary")
def summary():
    available=runs()
    if not available: return {"status":"not_run", "warning":"No authenticated GPU benchmark has been completed."}
    manifest=load(available[0]); summary_path=available[0].with_name("benchmark-summary.json")
    return {"manifest":manifest, "summary":load(summary_path) if summary_path.exists() else None}
@router.get("/api/gpu-lab/runs/{run_id}")
def run_detail(run_id: str):
    path=root()/run_id/"run-manifest.json"
    if not path.exists(): raise HTTPException(404, "GPU Lab run not found")
    return {"manifest":load(path), "summary":load(path.with_name("benchmark-summary.json"))}
@router.get("/api/gpu-lab/capabilities")
def capabilities(): return {"network_default":"disabled", "amd_smi":AmdSmiTelemetry().capabilities(), "providers":["mock","nvidia_nim","openai_compatible"]}
@router.get("/gpu-lab", response_class=HTMLResponse)
def dashboard():
    data=summary(); warning=data.get("warning") or ("Deterministic mock run — not a GPU benchmark." if data["manifest"].get("provider_mode")=="mock" else "")
    manifest=data.get("manifest", {})
    profile=manifest.get("resource_profile", "moderate")
    artifact=f"artifacts/gpu-lab/{manifest.get('run_id', '[run_id]')}/" if manifest else "artifacts/gpu-lab/[run_id]/"
    metrics=data.get("summary") or {}
    return HTMLResponse(f'''<!doctype html><html><head><title>AgentTrust GPU Reliability Lab</title><style>body{{font:16px system-ui;background:#07131f;color:#e8f1f7;max-width:980px;margin:auto;padding:32px}}.badge,.card{{background:#10283a;border:1px solid #35617a;border-radius:10px;padding:14px;margin:12px 0}}.badge{{color:#ffd585;font-weight:700}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}code{{color:#9de4c0}}h1{{margin-bottom:4px}}</style></head><body><h1>AgentTrust GPU Reliability Lab</h1><p class="badge">{'NOT RUN' if not manifest else manifest.get('run_mode','').upper()} · {profile.upper()}</p><section class="card"><strong>{warning}</strong><p>Evidence artifacts: <code>{artifact}</code></p></section><section class="grid"><div class="card">Provider<br><strong>{manifest.get('provider','Not measured')}</strong></div><div class="card">Verified hardware<br><strong>{manifest.get('verified_hardware_name','Not measured')}</strong></div><div class="card">Telemetry<br><strong>{manifest.get('telemetry_status','Telemetry unavailable')}</strong></div></section><section class="card"><strong>Operational evidence</strong><pre>{json.dumps(metrics, indent=2)}</pre></section></body></html>''')
