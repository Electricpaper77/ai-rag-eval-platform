import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.eval.regression import run_regression_eval


def _stub_query(question: str, top_k: int):
    text = question.lower()
    if "refund" in text:
        return {
            "answer": "Refunds are available within 30 days.",
            "citations": [{"source": "docs/refunds.md"}],
            "latency_ms": 12,
        }
    return {
        "answer": "I couldn’t find an answer in the documents.",
        "citations": [],
        "latency_ms": 34,
    }


def test_run_regression_eval_writes_jsonl(tmp_path: Path):
    dataset = [
        {"id": "refund", "question": "What is the refund policy?"},
        {"id": "shipping", "question": "What is the shipping timeline?"},
    ]
    variants = [
        {"name": "base", "prompt_prefix": ""},
        {"name": "grounded", "prompt_prefix": "Answer using documents."},
    ]

    summary = run_regression_eval(
        query_fn=_stub_query,
        dataset=dataset,
        variants=variants,
        top_k=2,
        run_id="test-run",
        artifact_dir=tmp_path,
    )

    output_file = Path(summary["output_file"])
    assert output_file.exists()

    lines = output_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(dataset) * len(variants)

    overall = summary["overall"]
    assert overall["total_cases"] == len(dataset) * len(variants)
    assert overall["citation_coverage_rate"] == pytest.approx(0.5)
    assert overall["refusal_rate"] == pytest.approx(0.5)
    assert overall["hallucination_rate"] == pytest.approx(0.0)

    sample = json.loads(lines[0])
    assert sample["run_id"] == "test-run"
    assert "variant" in sample
    assert "latency_ms" in sample


@pytest.mark.xfail(reason="TODO: detect hallucinations even when citations are present")
def test_hallucination_with_citations_todo(tmp_path: Path):
    dataset = [{"id": "q1", "question": "What is the refund policy?"}]
    variants = [{"name": "base", "prompt_prefix": ""}]

    def _stub_query_with_citation(question: str, top_k: int):
        return {
            "answer": "Unrelated made-up fact.",
            "citations": [{"source": "docs/refunds.md"}],
            "latency_ms": 5,
        }

    summary = run_regression_eval(
        query_fn=_stub_query_with_citation,
        dataset=dataset,
        variants=variants,
        run_id="todo-run",
        artifact_dir=tmp_path,
    )

    assert summary["overall"]["hallucination_rate"] == pytest.approx(1.0)
