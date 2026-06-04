from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval_harness import COST_ESTIMATE_LABEL, DEFAULT_HIRING_EVAL_CASES, run_eval_harness


def test_run_eval_harness_writes_recruiter_visible_jsonl(tmp_path: Path) -> None:
    output_path = tmp_path / "hiring_eval.jsonl"
    summary_path = tmp_path / "hiring_eval_summary.json"

    summary = run_eval_harness(
        output_path=output_path,
        summary_path=summary_path,
        run_id="test-hiring-eval",
    )

    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    case_rows = [row for row in rows if row["record_type"] == "case"]
    summary_row = rows[-1]

    assert output_path.exists()
    assert summary_path.exists()
    assert len(case_rows) == len(DEFAULT_HIRING_EVAL_CASES)
    assert summary_row["record_type"] == "summary"

    required_metrics = {
        "eval_pass_rate",
        "hallucination_rate",
        "citation_precision",
        "refusal_accuracy",
        "latency_p95_ms",
        "cost_per_request_usd",
    }
    assert required_metrics <= set(summary_row)
    assert required_metrics <= set(summary)

    assert summary_row["harness_run_id"] == "test-hiring-eval"
    assert summary_row["eval_pass_rate"] == pytest.approx(1.0)
    assert summary_row["hallucination_rate"] == pytest.approx(0.0)
    assert summary_row["citation_precision"] == pytest.approx(1.0)
    assert summary_row["refusal_accuracy"] == pytest.approx(1.0)
    assert summary_row["latency_p95_ms"] >= 0
    assert summary_row["cost_per_request_usd"] > 0
    assert summary_row["cost_estimate_label"] == COST_ESTIMATE_LABEL


def test_run_eval_harness_case_rows_include_evaluate_metrics(tmp_path: Path) -> None:
    output_path = tmp_path / "hiring_eval.jsonl"

    run_eval_harness(
        output_path=output_path,
        summary_path=None,
        run_id="case-contract",
    )

    first_case = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])

    assert first_case["record_type"] == "case"
    assert first_case["pass"] is True
    assert first_case["cost_estimate_label"] == COST_ESTIMATE_LABEL
    assert first_case["cost_per_request_usd"] > 0
    assert set(first_case["metrics"]) == {
        "hallucination_risk",
        "citation_coverage",
        "refusal_accuracy",
        "pii_leakage",
        "prompt_injection_compliance",
    }
