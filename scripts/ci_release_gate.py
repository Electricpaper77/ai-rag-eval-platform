"""CI adapter over the canonical B9 comparison gate."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.eval_harness import run_eval_harness
from app.regression_compare import compare, run_checksum
def run(name,cases):
 p=sum(x['pass'] for x in cases);v={'run_id':name,'cases':cases,'metrics':{'eval_pass_rate':p/len(cases),'hallucination_rate':0.,'citation_precision':1.,'refusal_accuracy':1.,'prompt_injection_defense_rate':1.,'latency_p95_ms':10.,'passed_cases':p,'failed_cases':len(cases)-p}};v['checksum']=run_checksum(v);return v
def fixtures(s):
 b=run('baseline-ci',[{'case_id':'citation','risk_category':'citation','pass':False},{'case_id':'injection','risk_category':'prompt_injection','pass':True}]);c=run('candidate-ci',[{'case_id':'citation','risk_category':'citation','pass':True},{'case_id':'injection','risk_category':'prompt_injection','pass':True}])
 if s=='block': c=run('candidate-ci',[c['cases'][0],{'case_id':'injection','risk_category':'prompt_injection','pass':False,'failure_reasons':['prompt-injection refusal failed']}])
 if s=='escalate': b=run('baseline-ci',[{'case_id':'citation','risk_category':'citation','pass':True},{'case_id':'injection','risk_category':'prompt_injection','pass':True}]);c=run('candidate-ci',[{'case_id':'citation','risk_category':'citation','pass':False,'failure_reasons':['citation missing']},c['cases'][1]])
 return b,c
def checkout_runs(base_sha=None):
 d=Path(tempfile.mkdtemp());out=[]
 for name in ('candidate-current-checkout',):
  s=run_eval_harness(d/f'{name}.jsonl',None,run_id=name);cases=[json.loads(x) for x in (d/f'{name}.jsonl').read_text().splitlines() if json.loads(x).get('record_type')=='case'];m={**s,'prompt_injection_defense_rate':next(x['metrics']['prompt_injection_compliance'] for x in cases if x['risk_category']=='prompt_injection'),'failed_cases':s['total_cases']-s['passed_cases']};v={'run_id':name,'cases':cases,'metrics':m,'candidate_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()};v['checksum']=run_checksum(v);out.append(v)
 candidate=out[0]
 if base_sha:
  raw=subprocess.check_output(['git','show',f'{base_sha}:docs/artifacts/eval_runs/hiring_eval.jsonl'],text=True)
  cases=[json.loads(x) for x in raw.splitlines() if json.loads(x).get('record_type')=='case']
  metrics=json.loads(subprocess.check_output(['git','show',f'{base_sha}:docs/artifacts/eval_runs/hiring_eval_summary.json'],text=True));metrics['prompt_injection_defense_rate']=next(x['metrics']['prompt_injection_compliance'] for x in cases if x['risk_category']=='prompt_injection');metrics['failed_cases']=metrics['total_cases']-metrics['passed_cases']
  baseline={'run_id':'baseline-base-sha','cases':cases,'metrics':metrics,'source_sha':base_sha};baseline['checksum']=run_checksum(baseline)
 else: baseline=candidate.copy();baseline['run_id']='baseline-local';baseline['checksum']=run_checksum(baseline)
 return baseline,candidate
def validate(r):
 p=r['proof'];assert p['baseline_run_id']==r['baseline']['run_id'] and p['candidate_run_id']==r['candidate']['run_id'];assert p['evidence']=={'baseline':r['baseline']['checksum'],'candidate':r['candidate']['checksum']};assert p['fixed_count']==r['counts']['FIXED'] and p['regression_count']==r['counts']['REGRESSED'] and p['decision']==r['decision']['value'];assert p['checksum']==hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='checksum'},sort_keys=True).encode()).hexdigest()
def main(argv=None):
 a=argparse.ArgumentParser();a.add_argument('--scenario',choices=('ship','block','escalate'));a.add_argument('--base-sha');a.add_argument('--output',type=Path,default=Path('artifacts/ci_release_proof.json'));x=a.parse_args(argv)
 try:
  r=compare(*(fixtures(x.scenario) if x.scenario else checkout_runs(x.base_sha)));validate(r);r['proof'].update(baseline_sha=r['baseline'].get('source_sha'),candidate_sha=r['candidate'].get('candidate_sha'));x.output.parent.mkdir(parents=True,exist_ok=True);x.output.write_text(json.dumps(r['proof'],indent=2,sort_keys=True)+'\n');m=r['metrics']['eval_pass_rate'];text=f"AGENTTRUST IQ RELEASE GATE\nBaseline: {r['baseline']['run_id']}\nCandidate: {r['candidate']['run_id']}\nPass rate: {m['baseline']:.1%} -> {m['candidate']:.1%} ({m['delta']*100:+.1f} pp)\nFixed: {r['counts']['FIXED']}\nRegressed: {r['counts']['REGRESSED']}\nDecision: {r['decision']['value']}\nChecksum: {r['proof']['checksum']}";print(text)
  if os.getenv('GITHUB_STEP_SUMMARY'):Path(os.environ['GITHUB_STEP_SUMMARY']).write_text('## '+text.replace('\n','\n\n'),encoding='utf-8')
  return 0 if r['decision']['value']=='SHIP' else 2
 except Exception as e: print(f'RELEASE GATE ERROR: {type(e).__name__}');return 3
if __name__=='__main__':raise SystemExit(main())
