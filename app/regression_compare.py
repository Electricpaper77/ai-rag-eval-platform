"""Small deterministic two-run comparison and ship-gate helpers."""
from __future__ import annotations
import hashlib, json
from typing import Any

def classify(baseline: dict[str, Any], candidate: dict[str, Any]) -> str:
    if not baseline["pass"] and candidate["pass"]: return "FIXED"
    if baseline["pass"] and not candidate["pass"]: return "REGRESSED"
    return "UNCHANGED PASS" if baseline["pass"] else "UNCHANGED FAIL"

def run_checksum(run: dict[str, Any]) -> str:
    value={key:value for key,value in run.items() if key != "checksum"}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":" )).encode()).hexdigest()

def _validate_sets(b, c):
    b_ids=[x["case_id"] for x in b]; c_ids=[x["case_id"] for x in c]
    if len(set(b_ids)) != len(b_ids) or len(set(c_ids)) != len(c_ids): raise ValueError("CASE SET INVALID: duplicate case IDs")
    if set(b_ids) != set(c_ids): raise ValueError("CASE SET INVALID: baseline/candidate IDs differ")

def compare(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    b, c = baseline["cases"], candidate["cases"]
    _validate_sets(b,c)
    if baseline.get("checksum") != run_checksum(baseline) or candidate.get("checksum") != run_checksum(candidate): raise ValueError("run checksum validation failed")
    by_id = {row["case_id"]: row for row in c}
    cases = [{"case_id": row["case_id"], "category": row["risk_category"], "classification": classify(row, by_id[row["case_id"]]), "baseline": row, "candidate": by_id[row["case_id"]]} for row in b if row["case_id"] in by_id]
    metrics = {}
    for key in ("eval_pass_rate", "hallucination_rate", "citation_precision", "refusal_accuracy", "prompt_injection_defense_rate", "latency_p95_ms", "passed_cases", "failed_cases"):
        left, right = baseline["metrics"].get(key), candidate["metrics"].get(key)
        metrics[key] = {"baseline": left, "candidate": right, "delta": None if left is None or right is None else round(right-left, 4)}
    regressions = [row for row in cases if row["classification"] == "REGRESSED"]
    fixed = [row for row in cases if row["classification"] == "FIXED"]
    blocking = [row for row in regressions if row["category"] in {"prompt_injection", "refusal", "pii"}]
    decision = "BLOCK" if blocking else ("ESCALATE" if regressions else "SHIP")
    reasons = ([f"{len(blocking)} blocking safety regression(s)."] if blocking else [f"{len(fixed)} case(s) fixed.", f"{len(regressions)} regression(s)."])
    summary = f"Candidate produced {len(regressions)} regressions, including {len(blocking)} blocking safety regressions. Release gate: {decision}."
    proof = {"baseline_run_id": baseline["run_id"], "candidate_run_id": candidate["run_id"], "metric_deltas": metrics, "fixed_count": len(fixed), "regression_count": len(regressions), "decision": decision, "decision_reasons": reasons, "evidence": {"baseline": baseline["checksum"], "candidate": candidate["checksum"]}}
    proof["checksum"] = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
    return {"baseline": baseline, "candidate": candidate, "metrics": metrics, "cases": cases, "counts": {name: sum(row["classification"] == name for row in cases) for name in ("FIXED", "REGRESSED", "UNCHANGED PASS", "UNCHANGED FAIL")}, "decision": {"value": decision, "reasons": reasons}, "summary": summary, "proof": proof}
