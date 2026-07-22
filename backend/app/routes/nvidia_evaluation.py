"""Lazy, read-only NVIDIA evaluation dashboard route."""
from __future__ import annotations
import json
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
router = APIRouter(tags=["nvidia-evaluation"])
ROOT = Path(__file__).resolve().parents[3]
@router.get("/api/nvidia-evaluation/summary")
def summary() -> dict:
    path = ROOT / "artifacts" / "benchmark-summary.json"
    if path.exists(): return json.loads(path.read_text(encoding="utf-8"))
    return {"status":"not_run","nvidia_requests":0,"case_count":50,"total_requests":0,"successful_requests":0,"eval_pass_rate":None,"hallucination_rate":None,"citation_precision":None,"refusal_accuracy":None,"prompt_injection_defense_rate":None,"latency_p95_ms":None}
@router.get("/nvidia-evaluation", response_class=HTMLResponse)
def page() -> str:
    return '''<!doctype html><title>AgentTrust IQ | NVIDIA Evaluation</title><style>body{margin:0;background:#07131f;color:#e7f1fa;font:16px Arial}header,main{max-width:1060px;margin:auto;padding:24px}header{max-width:none;background:#0c2030;border-bottom:1px solid #1c3d54}a{color:#76e4b1}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.card{padding:16px;background:#0c2030;border:1px solid #1c3d54;border-radius:10px}.value{font-size:24px;color:#76e4b1;margin-top:8px}.notice{padding:14px;background:#153042;border-left:4px solid #76e4b1}code{color:#bde9d2}</style><header><strong>AgentTrust IQ</strong> · <a href="/">Home</a> · <a href="/nvidia-evaluation">NVIDIA Evaluation</a></header><main><h1>NVIDIA Evaluation</h1><p><strong>50-case suite:</strong> 15 grounded RAG, 10 citation, 10 prompt-injection, 10 refusal, and 5 malformed-input cases.</p><p class="notice" id="status">API status: not_run. NVIDIA requests: 0. No benchmark metrics exist yet.</p><div class="grid" id="metrics"></div><p>Future authenticated smoke test (five requests): <code>NVIDIA_MODELS=&lt;model&gt; python -m nvidia_eval.runner --smoke-test --max-requests 5</code>.</p></main><script>const f=[['eval_pass_rate','Pass rate'],['hallucination_rate','Hallucination rate'],['citation_precision','Citation precision'],['refusal_accuracy','Refusal accuracy'],['prompt_injection_defense_rate','Injection defense'],['latency_p95_ms','Latency p95 (ms)']];fetch('/api/nvidia-evaluation/summary').then(r=>r.json()).then(x=>{status.textContent=x.status==='not_run'?'API status: not_run. NVIDIA requests: '+x.nvidia_requests+'. No benchmark metrics exist yet.':'Run status: '+x.status;metrics.innerHTML=f.map(([k,n])=>'<section class=card>'+n+'<div class=value>'+(x[k]===null?'—':k.includes('rate')||k.includes('precision')||k.includes('accuracy')?Math.round(x[k]*100)+'%':x[k])+'</div></section>').join('')})</script>'''
