"""Deterministic, evidence-backed evaluation decisions for Gate 23C."""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any


DECISIONS = ("PASS", "HOLD", "INSUFFICIENT_EVIDENCE")


def now():
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def recorded_metrics(run: dict[str, Any]) -> dict[str, float]:
    result = _json(run.get("result_json")) or {}
    values = result.get("quality_metrics")
    if not isinstance(values, dict):
        return {}
    return {key: value for key, value in values.items() if isinstance(key, str) and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))}


def evaluate(policy: dict[str, Any], current: dict[str, Any], baseline: dict[str, Any] | None) -> tuple[str, dict[str, Any], dict[str, Any]]:
    rules = _json(policy["metrics_json"]) or {}
    current_values = recorded_metrics(current)
    baseline_values = recorded_metrics(baseline) if baseline else {}
    missing_current = sorted(set(rules) - set(current_values))
    missing_baseline = sorted(set(rules) - set(baseline_values)) if policy["require_baseline"] else []
    if missing_current or missing_baseline:
        return "INSUFFICIENT_EVIDENCE", {
            "kind": "missing_evidence",
            "missing_current_metrics": missing_current,
            "missing_baseline_metrics": missing_baseline,
            "message": "Configured metrics and required baseline evidence were not all recorded.",
        }, {"current_run_id": current["id"], "baseline_run_id": baseline.get("id") if baseline else None}

    observations: dict[str, Any] = {}
    regressions: list[str] = []
    threshold_failures: list[str] = []
    for name, rule in rules.items():
        value = float(current_values[name])
        baseline_value = float(baseline_values[name]) if policy["require_baseline"] else None
        direction = rule["direction"]
        threshold = float(rule["threshold"])
        tolerance = float(rule.get("tolerance", 0.0))
        threshold_ok = value >= threshold if direction == "higher_is_better" else value <= threshold
        delta = value - baseline_value if baseline_value is not None else None
        regression = (delta < -tolerance) if direction == "higher_is_better" and delta is not None else ((delta > tolerance) if delta is not None else False)
        observations[name] = {
            "current": value,
            "baseline": baseline_value,
            "delta": delta,
            "direction": direction,
            "threshold": threshold,
            "tolerance": tolerance,
            "unit": rule.get("unit", ""),
            "threshold_passed": threshold_ok,
            "regression": regression,
        }
        if not threshold_ok:
            threshold_failures.append(name)
        if regression:
            regressions.append(name)
    decision = "HOLD" if threshold_failures or regressions else "PASS"
    rationale = {
        "kind": "evaluated",
        "message": "All configured evidence met policy thresholds and regression tolerances." if decision == "PASS" else "One or more configured metrics failed a threshold or regressed beyond tolerance.",
        "threshold_failures": threshold_failures,
        "regressions": regressions,
        "observations": observations,
    }
    refs = {"current_run_id": current["id"], "baseline_run_id": baseline.get("id") if baseline else None, "policy_id": policy["id"], "policy_version": policy["version"]}
    return decision, rationale, refs


def _require_membership(conn, organization_id: str, user_id: str, roles: tuple[str, ...] = ("owner", "admin", "member"), postgres: bool = True):
    placeholder = "%s" if postgres else "?"
    row = conn.execute(f"SELECT role FROM memberships WHERE organization_id={placeholder} AND user_id={placeholder} AND active=TRUE" if postgres else f"SELECT role FROM memberships WHERE organization_id={placeholder} AND user_id={placeholder}", (organization_id, user_id)).fetchone()
    if not row or row[0] not in roles:
        raise PermissionError("active organization membership required")
    return row[0]


def _scope_policy(conn, policy_id: str, organization_id: str, project_id: str, postgres: bool):
    p = "%s" if postgres else "?"
    row = conn.execute(f"SELECT id,organization_id,project_id,version,name,schema_version,metrics_json,require_baseline,created_by,created_at FROM evaluation_policies WHERE id={p} AND organization_id={p} AND project_id={p}", (policy_id, organization_id, project_id)).fetchone()
    if not row:
        raise PermissionError("policy is not authorized for this project")
    keys = ["id","organization_id","project_id","version","name","schema_version","metrics_json","require_baseline","created_by","created_at"]
    return dict(zip(keys, tuple(row)))


def _policy_payload(conn, organization_id: str, project_id: str, user_id: str, body: dict[str, Any], postgres: bool) -> dict[str, Any]:
    _require_membership(conn, organization_id, user_id, ("owner", "admin"), postgres)
    p = "%s" if postgres else "?"
    project = conn.execute(f"SELECT id FROM projects WHERE id={p} AND organization_id={p}", (project_id, organization_id)).fetchone()
    if not project:
        raise KeyError("project not found")
    name = str(body["name"])
    metrics = body["metrics"]
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("at least one metric rule is required")
    normalized = {}
    for key, rule in metrics.items():
        if not isinstance(key, str) or not key or len(key) > 64 or not isinstance(rule, dict):
            raise ValueError("invalid metric rule")
        direction = rule.get("direction")
        if direction not in ("higher_is_better", "lower_is_better"):
            raise ValueError("metric direction must be higher_is_better or lower_is_better")
        try:
            threshold = float(rule["threshold"])
            tolerance = float(rule.get("tolerance", 0.0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("metric thresholds must be numeric") from exc
        if not math.isfinite(threshold) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("metric thresholds must be finite and tolerance non-negative")
        normalized[key] = {"direction": direction, "threshold": threshold, "tolerance": tolerance, "unit": str(rule.get("unit", ""))[:32]}
    lock = f"policy:{organization_id}:{project_id}:{name}"
    if postgres:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock,))
    latest = conn.execute(f"SELECT COALESCE(MAX(version),0) FROM evaluation_policies WHERE organization_id={p} AND project_id={p} AND name={p}", (organization_id, project_id, name)).fetchone()[0]
    payload = {"id": new_id("pol"), "organization_id": organization_id, "project_id": project_id, "version": int(latest) + 1, "name": name, "schema_version": "gate23c-v1", "metrics_json": json.dumps(normalized, sort_keys=True), "require_baseline": bool(body.get("require_baseline", True)), "created_by": user_id, "created_at": now()}
    conn.execute(f"INSERT INTO evaluation_policies (id,organization_id,project_id,version,name,schema_version,metrics_json,require_baseline,created_by,created_at) VALUES ({','.join([p]*10)})", tuple(payload.values()))
    return payload


def create_policy_pg(conn, organization_id: str, project_id: str, user_id: str, body: dict[str, Any]):
    with conn.transaction():
        return _policy_payload(conn, organization_id, project_id, user_id, body, True)


def create_policy_sqlite(conn, organization_id: str, project_id: str, user_id: str, body: dict[str, Any]):
    conn.execute("BEGIN IMMEDIATE")
    try:
        result = _policy_payload(conn, organization_id, project_id, user_id, body, False)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def _run(conn, run_id: str, organization_id: str, postgres: bool):
    p = "%s" if postgres else "?"
    row = conn.execute(f"SELECT r.id,r.organization_id,r.project_id,r.status,e.result_json,e.evidence_metadata_json FROM evaluation_runs r LEFT JOIN evaluation_results e ON e.run_id=r.id WHERE r.id={p} AND r.organization_id={p}", (run_id, organization_id)).fetchone()
    if not row:
        raise PermissionError("evaluation is not authorized for this organization")
    keys = ["id","organization_id","project_id","status","result_json","evidence_metadata_json"]
    return dict(zip(keys, tuple(row)))


def _decision(conn, decision_id: str, organization_id: str, postgres: bool):
    p = "%s" if postgres else "?"
    row = conn.execute(f"SELECT id,organization_id,project_id,current_run_id,baseline_run_id,policy_id,policy_version,idempotency_key,decision,rationale_json,evidence_refs_json,created_by,created_at FROM evaluation_decisions WHERE id={p} AND organization_id={p}", (decision_id, organization_id)).fetchone()
    if not row:
        return None
    keys = ["id","organization_id","project_id","current_run_id","baseline_run_id","policy_id","policy_version","idempotency_key","decision","rationale_json","evidence_refs_json","created_by","created_at"]
    result = dict(zip(keys, tuple(row)))
    result["rationale"] = _json(result.pop("rationale_json"))
    result["evidence_refs"] = _json(result.pop("evidence_refs_json"))
    return result


def create_decision_pg(conn, organization_id: str, current_run_id: str, user_id: str, body: dict[str, Any]):
    with conn.transaction():
        _require_membership(conn, organization_id, user_id, postgres=True)
        idem = body["idempotency_key"]
        existing = conn.execute("SELECT id FROM evaluation_decisions WHERE organization_id=%s AND idempotency_key=%s", (organization_id, idem)).fetchone()
        if existing:
            return _decision(conn, existing[0], organization_id, True)
        current = _run(conn, current_run_id, organization_id, True)
        baseline = _run(conn, body.get("baseline_run_id"), organization_id, True) if body.get("baseline_run_id") else None
        if baseline and baseline["project_id"] != current["project_id"]:
            raise ValueError("baseline must belong to the current project")
        policy = _scope_policy(conn, body["policy_id"], organization_id, current["project_id"], True)
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"decision:{organization_id}:{current_run_id}:{policy['id']}",))
        existing = conn.execute("SELECT id FROM evaluation_decisions WHERE organization_id=%s AND current_run_id=%s AND policy_id=%s", (organization_id, current_run_id, policy["id"])).fetchone()
        if existing:
            return _decision(conn, existing[0], organization_id, True)
        status, rationale, refs = evaluate(policy, current, baseline)
        decision_id = new_id("dec")
        conn.execute("INSERT INTO evaluation_decisions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (decision_id,organization_id,current["project_id"],current_run_id,body.get("baseline_run_id"),policy["id"],policy["version"],idem,status,json.dumps(rationale,sort_keys=True),json.dumps(refs,sort_keys=True),user_id,now()))
        return _decision(conn, decision_id, organization_id, True)


def create_decision_sqlite(conn, organization_id: str, current_run_id: str, user_id: str, body: dict[str, Any]):
    conn.execute("BEGIN IMMEDIATE")
    try:
        _require_membership(conn, organization_id, user_id, postgres=False)
        existing = conn.execute("SELECT id FROM evaluation_decisions WHERE organization_id=? AND idempotency_key=?", (organization_id, body["idempotency_key"])).fetchone()
        if existing:
            result = _decision(conn, existing[0], organization_id, False); conn.commit(); return result
        current = _run(conn, current_run_id, organization_id, False)
        baseline = _run(conn, body.get("baseline_run_id"), organization_id, False) if body.get("baseline_run_id") else None
        if baseline and baseline["project_id"] != current["project_id"]:
            raise ValueError("baseline must belong to the current project")
        policy = _scope_policy(conn, body["policy_id"], organization_id, current["project_id"], False)
        existing = conn.execute("SELECT id FROM evaluation_decisions WHERE organization_id=? AND current_run_id=? AND policy_id=?", (organization_id, current_run_id, policy["id"])).fetchone()
        if existing:
            result = _decision(conn, existing[0], organization_id, False); conn.commit(); return result
        status, rationale, refs = evaluate(policy, current, baseline)
        decision_id = new_id("dec")
        conn.execute("INSERT INTO evaluation_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (decision_id,organization_id,current["project_id"],current_run_id,body.get("baseline_run_id"),policy["id"],policy["version"],body["idempotency_key"],status,json.dumps(rationale,sort_keys=True),json.dumps(refs,sort_keys=True),user_id,now().isoformat()))
        conn.commit()
        return _decision(conn, decision_id, organization_id, False)
    except Exception:
        conn.rollback()
        raise


def list_decisions(conn, organization_id: str, user_id: str, project_id: str | None, page: int, page_size: int, postgres: bool):
    _require_membership(conn, organization_id, user_id, postgres=postgres)
    p = "%s" if postgres else "?"
    page = max(1, page); page_size = min(100, max(1, page_size)); offset = (page - 1) * page_size; params: list[Any] = [organization_id]
    clause = f"organization_id={p}"
    if project_id:
        clause += f" AND project_id={p}"; params.append(project_id)
    total = conn.execute(f"SELECT COUNT(*) FROM evaluation_decisions WHERE {clause}", tuple(params)).fetchone()[0]
    rows = conn.execute(f"SELECT id,project_id,current_run_id,baseline_run_id,policy_id,policy_version,decision,created_at FROM evaluation_decisions WHERE {clause} ORDER BY created_at DESC LIMIT {page_size} OFFSET {offset}", tuple(params)).fetchall()
    return {"decisions": [dict(zip(["id","project_id","current_run_id","baseline_run_id","policy_id","policy_version","decision","created_at"], tuple(row))) for row in rows], "page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}


def get_decision_pg(conn, organization_id: str, user_id: str, decision_id: str):
    with conn.transaction():
        _require_membership(conn, organization_id, user_id, postgres=True)
        result = _decision(conn, decision_id, organization_id, True)
        if not result: raise KeyError("decision not found")
        return result


def get_decision_sqlite(conn, organization_id: str, user_id: str, decision_id: str):
    _require_membership(conn, organization_id, user_id, postgres=False)
    result = _decision(conn, decision_id, organization_id, False)
    if not result: raise KeyError("decision not found")
    return result

