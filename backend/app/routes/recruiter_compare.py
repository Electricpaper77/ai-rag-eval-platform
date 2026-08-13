"""Read-only deterministic recruiter comparison backed by the B9 canonical result."""
from __future__ import annotations
import json, tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from app.regression_compare import compare

router=APIRouter(tags=["recruiter-compare"])
PROOF=Path(tempfile.gettempdir())/"agenttrust-iq-comparison-proof.json"

def _run(run_id, cases):
    passed=sum(c["pass"] for c in cases); total=len(cases)
    return {"run_id":run_id,"pack":"canonical_hiring_eval","mode":"deterministic demo / no external API key","checksum":run_id+"-checksum","cases":cases,"metrics":{"eval_pass_rate":passed/total,"hallucination_rate":0.0,"citation_precision":1.0,"refusal_accuracy":1.0,"prompt_injection_defense_rate":1.0,"latency_p95_ms":10.0,"passed_cases":passed,"failed_cases":total-passed}}
def _result():
    base=_run("baseline-demo",[{"case_id":"citation-1","risk_category":"citation","pass":False,"failure_reasons":["citation missing"]},{"case_id":"citation-2","risk_category":"citation","pass":True},{"case_id":"injection-1","risk_category":"prompt_injection","pass":True}])
    cand=_run("candidate-demo",[{"case_id":"citation-1","risk_category":"citation","pass":True},{"case_id":"citation-2","risk_category":"citation","pass":True},{"case_id":"injection-1","risk_category":"prompt_injection","pass":False,"failure_reasons":["injection refusal failed"]}])
    result=compare(base,cand); result["proof"].update(schema_version=1,generated_at="deterministic-demo",evaluation_pack="canonical_hiring_eval",unchanged_counts=result["counts"])
    return result
def _persist():
    result=_result(); PROOF.write_text(json.dumps(result["proof"],indent=2,sort_keys=True),encoding="utf-8"); return result
@router.get("/api/compare")
def api_compare(baseline:str="baseline-demo",candidate:str="candidate-demo"):
    if (baseline,candidate)!=("baseline-demo","candidate-demo"): raise HTTPException(404,"Unknown or incomplete comparison run IDs.")
    return _persist()
@router.get("/api/compare/proof")
def proof():
    if not PROOF.exists(): _persist()
    try: json.loads(PROOF.read_text())
    except json.JSONDecodeError as exc: raise HTTPException(500,"Comparison proof is invalid.") from exc
    return FileResponse(PROOF,filename="comparison-proof.json")
@router.get("/compare",response_class=HTMLResponse)
def page():
    return '''<!doctype html><title>Regression Comparison</title><main><h1>Regression Comparison</h1><p><b>Deterministic Demo</b> · No external API key required</p><div id=app>Loading comparison…</div><script>fetch('/api/compare'+location.search).then(async r=>{{if(!r.ok)throw Error((await r.json()).detail);return r.json()}}).then(d=>{{let p=x=>x==null?'N/A':typeof x=='number'&&Math.abs(x)<=1?(x*100).toFixed(1)+'%':x;document.querySelector('#app').innerHTML=`<h2>Final decision: ${{d.decision.value}}</h2><ul>${{d.decision.reasons.map(x=>`<li>${{x}}</li>`).join('')}}</ul><p>${{d.summary}}</p><h2>Baseline: ${{d.baseline.run_id}} · Candidate: ${{d.candidate.run_id}}</h2><table><tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Delta</th></tr>${{Object.entries(d.metrics).map(([k,v])=>`<tr><td>${{k}}</td><td>${{p(v.baseline)}}</td><td>${{p(v.candidate)}}</td><td>${{p(v.delta)}}${{k.includes('rate')||k.includes('precision')||k.includes('accuracy')?' percentage points':''}}</td></tr>`).join('')}}</table><h2>Cases</h2>${{d.cases.sort((a,b)=>['REGRESSED','FIXED','UNCHANGED FAIL','UNCHANGED PASS'].indexOf(a.classification)-['REGRESSED','FIXED','UNCHANGED FAIL','UNCHANGED PASS'].indexOf(b.classification)).map(c=>`<details><summary>${{c.classification}} — ${{c.case_id}}</summary><pre>${{JSON.stringify(c,null,2)}}</pre></details>`).join('')}}<p><a href=/api/compare/proof>View Comparison Proof</a></p>`}}).catch(e=>document.querySelector('#app').textContent='Comparison unavailable: '+e.message)</script></main>'''
