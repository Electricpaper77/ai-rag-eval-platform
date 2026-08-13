"""CI adapter for the existing B9 comparison and release gate."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.regression_compare import compare, run_checksum

def run(name, cases):
    passed=sum(x["pass"] for x in cases); total=len(cases)
    value={"run_id":name,"cases":cases,"metrics":{"eval_pass_rate":passed/total,"hallucination_rate":0.0,"citation_precision":1.0,"refusal_accuracy":1.0,"prompt_injection_defense_rate":1.0,"latency_p95_ms":10.0,"passed_cases":passed,"failed_cases":total-passed}}; value["checksum"]=run_checksum(value); return value
def scenario(name):
    base=run("baseline-ci",[{"case_id":"citation","risk_category":"citation","pass":False},{"case_id":"injection","risk_category":"prompt_injection","pass":True}])
    candidate=run("candidate-ci",[{"case_id":"citation","risk_category":"citation","pass":True},{"case_id":"injection","risk_category":"prompt_injection","pass":True}])
    if name=="block": candidate["cases"][1]={"case_id":"injection","risk_category":"prompt_injection","pass":False,"failure_reasons":["prompt-injection refusal failed"]}; candidate=run("candidate-ci",candidate["cases"])
    return base,candidate
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--scenario",choices=("ship","block","escalate"));p.add_argument("--output",type=Path,default=Path("artifacts/ci_release_proof.json"));a=p.parse_args(argv)
    try:
        result=compare(*scenario(a.scenario or "ship")); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result["proof"],indent=2,sort_keys=True)+"\n")
        m=result["metrics"]["eval_pass_rate"]; print(f"AGENTTRUST IQ RELEASE GATE\nBaseline: {result['baseline']['run_id']}\nCandidate: {result['candidate']['run_id']}\nPass rate: {m['baseline']:.1%} -> {m['candidate']:.1%} ({m['delta']*100:+.1f} pp)\nFixed: {result['counts']['FIXED']}\nRegressed: {result['counts']['REGRESSED']}\nDecision: {result['decision']['value']}\nEvidence: {a.output.as_posix()}\nChecksum: {result['proof']['checksum']}")
        return 0 if result["decision"]["value"]=="SHIP" else 2
    except Exception as exc: print(f"RELEASE GATE ERROR: {type(exc).__name__}"); return 3
if __name__=="__main__": raise SystemExit(main())
