import json
from app.regression_compare import compare

def run(name, cases):
    metrics={"eval_pass_rate":sum(x["pass"] for x in cases)/len(cases),"hallucination_rate":0.0,"citation_precision":1.0,"refusal_accuracy":1.0,"prompt_injection_defense_rate":1.0,"latency_p95_ms":10.0,"passed_cases":sum(x["pass"] for x in cases),"failed_cases":sum(not x["pass"] for x in cases)}
    return {"run_id":name,"metrics":metrics,"cases":cases,"checksum":name+"-hash"}

def test_two_run_deltas_case_diff_and_ship_gate():
    base=run("baseline",[{"case_id":"a","risk_category":"citation","pass":False},{"case_id":"b","risk_category":"citation","pass":True},{"case_id":"c","risk_category":"refusal","pass":False},{"case_id":"d","risk_category":"pii","pass":False}])
    candidate=run("candidate",[{"case_id":"a","risk_category":"citation","pass":True},{"case_id":"b","risk_category":"citation","pass":True},{"case_id":"c","risk_category":"refusal","pass":False},{"case_id":"d","risk_category":"pii","pass":True}])
    result=compare(base,candidate)
    assert result["counts"] == {"FIXED":2,"REGRESSED":0,"UNCHANGED PASS":1,"UNCHANGED FAIL":1}
    assert result["metrics"]["eval_pass_rate"]["delta"] == .5
    assert result["decision"]["value"] == "SHIP"
    assert result["proof"]["baseline_run_id"] == "baseline"

def test_safety_regression_blocks_and_missing_metrics_are_na():
    base=run("b",[{"case_id":"s","risk_category":"prompt_injection","pass":True}]); candidate=run("c",[{"case_id":"s","risk_category":"prompt_injection","pass":False}]); candidate["metrics"].pop("citation_precision")
    result=compare(base,candidate)
    assert result["counts"]["REGRESSED"] == 1 and result["decision"]["value"] == "BLOCK"
    assert result["metrics"]["citation_precision"]["delta"] is None
