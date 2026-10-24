"""Tenant-scoped Gate 23D investigation and release-review persistence.

Case evidence is only returned when a persisted source row exists.  The API never
derives a failed case from aggregate metrics, and a release review is an immutable
review record rather than a deployment or promotion authorization.

# Gate 23D evidence remains synthetic/disposable and is not a production release gate.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .repository import use_postgres


class ReviewConflict(ValueError):
    pass


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _case(row: Any, postgres: bool) -> dict[str, Any]:
    keys = ["id", "organization_id", "project_id", "run_id", "case_key", "status", "failure_category", "score", "evidence", "evidence_digest", "provenance", "created_at"]
    item = dict(zip(keys, tuple(row)))
    item["evidence"] = _json(item["evidence"])
    item["evidence_status"] = "AVAILABLE" if item["evidence"] not in (None, {}, []) else "MISSING_EVIDENCE"
    if hasattr(item["created_at"], "isoformat"):
        item["created_at"] = item["created_at"].isoformat()
    return item


def _review(row: Any) -> dict[str, Any]:
    keys = ["id", "case_id", "organization_id", "project_id", "run_id", "revision", "status", "comment", "provenance", "reviewer_id", "idempotency_key", "created_at"]
    item = dict(zip(keys, tuple(row)))
    if hasattr(item["created_at"], "isoformat"):
        item["created_at"] = item["created_at"].isoformat()
    return item


def _release(row: Any) -> dict[str, Any]:
    keys = ["id", "organization_id", "project_id", "decision_id", "policy_id", "policy_version", "current_run_id", "baseline_run_id", "recommendation", "decision_status", "rationale", "evidence_refs", "evidence_digest", "reviewer_id", "idempotency_key", "created_at"]
    item = dict(zip(keys, tuple(row)))
    item["rationale"] = _json(item["rationale"])
    item["evidence_refs"] = _json(item["evidence_refs"])
    if hasattr(item["created_at"], "isoformat"):
        item["created_at"] = item["created_at"].isoformat()
    return item


def _case_select(postgres: bool) -> str:
    return "SELECT id,organization_id,project_id,run_id,case_key,status,failure_category,score,evidence_json,evidence_digest,provenance,created_at FROM evaluation_cases"


def list_cases(organization_id: str, project_id: str, run_id: str, user_id: str, status: str = "", failure_category: str = "", page: int = 1, page_size: int = 20) -> dict[str, Any]:
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    if use_postgres():
        from .postgres_repository import protected_connect, require_membership
        with protected_connect() as conn:
            with conn.transaction():
                require_membership(conn, organization_id, user_id)
                if not conn.execute("SELECT 1 FROM evaluation_runs WHERE id=%s AND organization_id=%s AND project_id=%s", (run_id, organization_id, project_id)).fetchone():
                    raise KeyError("evaluation not found")
                clauses = ["organization_id=%s", "project_id=%s", "run_id=%s"]
                params: list[Any] = [organization_id, project_id, run_id]
                if status:
                    clauses.append("status=%s"); params.append(status)
                if failure_category:
                    clauses.append("failure_category=%s"); params.append(failure_category)
                where = " AND ".join(clauses)
                total = conn.execute(f"SELECT COUNT(*) FROM evaluation_cases WHERE {where}", tuple(params)).fetchone()[0]
                rows = conn.execute(f"{_case_select(True)} WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s", tuple(params + [page_size, (page - 1) * page_size])).fetchall()
    else:
        from .repository import connect, require_membership
        conn = connect()
        try:
            require_membership(conn, organization_id, user_id)
            if not conn.execute("SELECT 1 FROM evaluation_runs WHERE id=? AND organization_id=? AND project_id=?", (run_id, organization_id, project_id)).fetchone():
                raise KeyError("evaluation not found")
            clauses = ["organization_id=?", "project_id=?", "run_id=?"]
            params = [organization_id, project_id, run_id]
            if status:
                clauses.append("status=?"); params.append(status)
            if failure_category:
                clauses.append("failure_category=?"); params.append(failure_category)
            where = " AND ".join(clauses)
            total = conn.execute(f"SELECT COUNT(*) FROM evaluation_cases WHERE {where}", tuple(params)).fetchone()[0]
            rows = conn.execute(f"{_case_select(False)} WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?", tuple(params + [page_size, (page - 1) * page_size])).fetchall()
        finally:
            conn.close()
    items = [_case(row, use_postgres()) for row in rows]
    return {"cases": items, "evidence_status": "AVAILABLE" if items else "MISSING_EVIDENCE", "message": None if items else "No persisted per-case evidence is available for this run.", "page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}


def _case_for_update(conn: Any, organization_id: str, case_id: str, postgres: bool) -> Any:
    placeholder = "%s" if postgres else "?"
    return conn.execute(f"SELECT id,organization_id,project_id,run_id,case_key,status,failure_category,score,evidence_json,evidence_digest,provenance,created_at FROM evaluation_cases WHERE id={placeholder} AND organization_id={placeholder} FOR SHARE" if postgres else f"SELECT id,organization_id,project_id,run_id,case_key,status,failure_category,score,evidence_json,evidence_digest,provenance,created_at FROM evaluation_cases WHERE id=? AND organization_id=?", (case_id, organization_id)).fetchone()


def create_case_review(case_id: str, organization_id: str, user_id: str, status: str, comment: str, expected_revision: int, idempotency_key: str) -> dict[str, Any]:
    if status not in {"open", "confirmed", "rejected", "hold"}:
        raise ValueError("invalid review status")
    comment = comment.strip()
    if not comment or len(comment) > 4000:
        raise ValueError("review comment must be 1-4000 characters")
    if not idempotency_key or len(idempotency_key) > 120:
        raise ValueError("idempotency_key must be 1-120 characters")
    postgres = use_postgres()
    if postgres:
        from .postgres_repository import protected_connect, require_membership
        with protected_connect() as conn:
            with conn.transaction():
                require_membership(conn, organization_id, user_id, ("owner", "admin"))
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"case-review:{organization_id}:{case_id}",))
                existing = conn.execute("SELECT id,case_id,organization_id,project_id,run_id,revision,status,comment,provenance,reviewer_id,idempotency_key,created_at FROM evaluation_case_review_revisions WHERE organization_id=%s AND idempotency_key=%s", (organization_id, idempotency_key)).fetchone()
                if existing:
                    if existing[1] != case_id: raise ReviewConflict("idempotency key is bound to another case")
                    return _review(existing)
                case = _case_for_update(conn, organization_id, case_id, True)
                if not case: raise KeyError("case not found")
                if case[8] is None: raise ValueError("case evidence is missing")
                current = conn.execute("SELECT COALESCE(MAX(revision),0) FROM evaluation_case_review_revisions WHERE case_id=%s", (case_id,)).fetchone()[0]
                if int(current) != expected_revision: raise ReviewConflict(f"review revision conflict: expected {expected_revision}, current {current}")
                review_id = _id("review"); ts = _now()
                conn.execute("INSERT INTO evaluation_case_review_revisions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (review_id, case_id, organization_id, case[2], case[3], int(current)+1, status, comment, "reviewer_confirmed", user_id, idempotency_key, ts))
                row = conn.execute("SELECT id,case_id,organization_id,project_id,run_id,revision,status,comment,provenance,reviewer_id,idempotency_key,created_at FROM evaluation_case_review_revisions WHERE id=%s", (review_id,)).fetchone()
                return _review(row)
    from .repository import connect, require_membership
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        require_membership(conn, organization_id, user_id, ("owner", "admin"))
        existing = conn.execute("SELECT id,case_id,organization_id,project_id,run_id,revision,status,comment,provenance,reviewer_id,idempotency_key,created_at FROM evaluation_case_review_revisions WHERE organization_id=? AND idempotency_key=?", (organization_id, idempotency_key)).fetchone()
        if existing:
            if existing[1] != case_id: raise ReviewConflict("idempotency key is bound to another case")
            return _review(existing)
        case = _case_for_update(conn, organization_id, case_id, False)
        if not case: raise KeyError("case not found")
        if case[8] is None: raise ValueError("case evidence is missing")
        current = conn.execute("SELECT COALESCE(MAX(revision),0) FROM evaluation_case_review_revisions WHERE case_id=?", (case_id,)).fetchone()[0]
        if int(current) != expected_revision: raise ReviewConflict(f"review revision conflict: expected {expected_revision}, current {current}")
        review_id = _id("review"); ts = _now()
        conn.execute("INSERT INTO evaluation_case_review_revisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (review_id, case_id, organization_id, case[2], case[3], int(current)+1, status, comment, "reviewer_confirmed", user_id, idempotency_key, ts)); conn.commit()
        return _review(conn.execute("SELECT id,case_id,organization_id,project_id,run_id,revision,status,comment,provenance,reviewer_id,idempotency_key,created_at FROM evaluation_case_review_revisions WHERE id=?", (review_id,)).fetchone())
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def list_case_reviews(case_id: str, organization_id: str, user_id: str) -> list[dict[str, Any]]:
    postgres = use_postgres()
    if postgres:
        from .postgres_repository import protected_connect, require_membership
        with protected_connect() as conn:
            with conn.transaction():
                require_membership(conn, organization_id, user_id)
                rows = conn.execute("SELECT id,case_id,organization_id,project_id,run_id,revision,status,comment,provenance,reviewer_id,idempotency_key,created_at FROM evaluation_case_review_revisions WHERE case_id=%s AND organization_id=%s ORDER BY revision", (case_id, organization_id)).fetchall()
    else:
        from .repository import connect, require_membership
        conn = connect()
        try:
            require_membership(conn, organization_id, user_id)
            rows = conn.execute("SELECT id,case_id,organization_id,project_id,run_id,revision,status,comment,provenance,reviewer_id,idempotency_key,created_at FROM evaluation_case_review_revisions WHERE case_id=? AND organization_id=? ORDER BY revision", (case_id, organization_id)).fetchall()
        finally: conn.close()
    if not rows:
        raise KeyError("case reviews not found")
    return [_review(row) for row in rows]


def create_release_review(organization_id: str, project_id: str, user_id: str, decision_id: str, recommendation: str, idempotency_key: str) -> dict[str, Any]:
    if recommendation not in {"acknowledge", "hold"}:
        raise ValueError("recommendation must be acknowledge or hold")
    if not idempotency_key or len(idempotency_key) > 120:
        raise ValueError("idempotency_key must be 1-120 characters")
    postgres = use_postgres()
    if postgres:
        from .postgres_repository import protected_connect, require_membership
        with protected_connect() as conn:
            with conn.transaction():
                require_membership(conn, organization_id, user_id, ("owner", "admin"))
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"release-review:{organization_id}:{idempotency_key}",))
                existing = conn.execute("SELECT id,organization_id,project_id,decision_id,policy_id,policy_version,current_run_id,baseline_run_id,recommendation,decision_status,rationale_json,evidence_refs_json,evidence_digest,reviewer_id,idempotency_key,created_at FROM release_reviews WHERE organization_id=%s AND idempotency_key=%s", (organization_id, idempotency_key)).fetchone()
                if existing: return _release(existing)
                decision = conn.execute("SELECT id,project_id,current_run_id,baseline_run_id,policy_id,policy_version,decision,rationale_json,evidence_refs_json FROM evaluation_decisions WHERE id=%s AND organization_id=%s AND project_id=%s", (decision_id, organization_id, project_id)).fetchone()
                if not decision: raise KeyError("decision not found")
                snapshot = {"decision_id": decision[0], "policy_id": decision[4], "policy_version": decision[5], "current_run_id": decision[2], "baseline_run_id": decision[3], "decision": decision[6], "rationale": _json(decision[7]), "evidence_refs": _json(decision[8])}
                review_id = _id("release"); ts = _now(); digest = _digest(snapshot)
                conn.execute("INSERT INTO release_reviews VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (review_id, organization_id, project_id, decision_id, decision[4], decision[5], decision[2], decision[3], recommendation, decision[6], json.dumps(snapshot["rationale"], sort_keys=True), json.dumps(snapshot["evidence_refs"], sort_keys=True), digest, user_id, idempotency_key, ts))
                return _release(conn.execute("SELECT id,organization_id,project_id,decision_id,policy_id,policy_version,current_run_id,baseline_run_id,recommendation,decision_status,rationale_json,evidence_refs_json,evidence_digest,reviewer_id,idempotency_key,created_at FROM release_reviews WHERE id=%s", (review_id,)).fetchone())
    from .repository import connect, require_membership
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE"); require_membership(conn, organization_id, user_id, ("owner", "admin"))
        existing = conn.execute("SELECT id,organization_id,project_id,decision_id,policy_id,policy_version,current_run_id,baseline_run_id,recommendation,decision_status,rationale_json,evidence_refs_json,evidence_digest,reviewer_id,idempotency_key,created_at FROM release_reviews WHERE organization_id=? AND idempotency_key=?", (organization_id, idempotency_key)).fetchone()
        if existing: return _release(existing)
        decision = conn.execute("SELECT id,project_id,current_run_id,baseline_run_id,policy_id,policy_version,decision,rationale_json,evidence_refs_json FROM evaluation_decisions WHERE id=? AND organization_id=? AND project_id=?", (decision_id, organization_id, project_id)).fetchone()
        if not decision: raise KeyError("decision not found")
        snapshot = {"decision_id": decision[0], "policy_id": decision[4], "policy_version": decision[5], "current_run_id": decision[2], "baseline_run_id": decision[3], "decision": decision[6], "rationale": _json(decision[7]), "evidence_refs": _json(decision[8])}
        review_id = _id("release"); ts = _now(); digest = _digest(snapshot)
        conn.execute("INSERT INTO release_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (review_id, organization_id, project_id, decision_id, decision[4], decision[5], decision[2], decision[3], recommendation, decision[6], json.dumps(snapshot["rationale"], sort_keys=True), json.dumps(snapshot["evidence_refs"], sort_keys=True), digest, user_id, idempotency_key, ts)); conn.commit()
        return _release(conn.execute("SELECT id,organization_id,project_id,decision_id,policy_id,policy_version,current_run_id,baseline_run_id,recommendation,decision_status,rationale_json,evidence_refs_json,evidence_digest,reviewer_id,idempotency_key,created_at FROM release_reviews WHERE id=?", (review_id,)).fetchone())
    except Exception:
        conn.rollback(); raise
    finally: conn.close()


def get_release_review(review_id: str, organization_id: str, user_id: str) -> dict[str, Any]:
    postgres = use_postgres()
    if postgres:
        from .postgres_repository import protected_connect, require_membership
        with protected_connect() as conn:
            with conn.transaction():
                require_membership(conn, organization_id, user_id)
                row = conn.execute("SELECT id,organization_id,project_id,decision_id,policy_id,policy_version,current_run_id,baseline_run_id,recommendation,decision_status,rationale_json,evidence_refs_json,evidence_digest,reviewer_id,idempotency_key,created_at FROM release_reviews WHERE id=%s AND organization_id=%s", (review_id, organization_id)).fetchone()
    else:
        from .repository import connect, require_membership
        conn = connect()
        try:
            require_membership(conn, organization_id, user_id)
            row = conn.execute("SELECT id,organization_id,project_id,decision_id,policy_id,policy_version,current_run_id,baseline_run_id,recommendation,decision_status,rationale_json,evidence_refs_json,evidence_digest,reviewer_id,idempotency_key,created_at FROM release_reviews WHERE id=? AND organization_id=?", (review_id, organization_id)).fetchone()
        finally: conn.close()
    if not row: raise KeyError("release review not found")
    return _release(row)

