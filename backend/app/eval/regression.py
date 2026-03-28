import json
import logging
import math
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DATASET = [
    {"id": "refund_1", "question": "What is the refund policy?"},
    {"id": "ship_1", "question": "How long does shipping take?"},
    {"id": "support_1", "question": "What are the support hours?"},
]

PROMPT_VARIANTS = [
    {"name": "base", "prompt_prefix": ""},
    {
        "name": "grounded",
        "prompt_prefix": "Answer using only the provided documents and cite sources.",
    },
    {
        "name": "concise",
        "prompt_prefix": "Provide a concise, factual answer based on the documents.",
    },
]

REFUSAL_PHRASES = [
    "i cannot",
    "i can't",
    "unable to",
    "i couldn’t",
    "i couldn't",
    "no results",
    "not found in the documents",
    "could not find",
    "cannot find",
    "i do not have",
]


def _nearest_rank(values: List[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _apply_prompt(prompt_prefix: str, question: str) -> str:
    prefix = (prompt_prefix or "").strip()
    if not prefix:
        return question
    return f"{prefix}\n\nQuestion: {question}"


def _is_refusal(answer: str) -> bool:
    text = (answer or "").lower()
    return any(phrase in text for phrase in REFUSAL_PHRASES)


def _is_hallucination(answer: str, citations: Iterable[Any]) -> bool:
    has_citations = bool(list(citations))
    if _is_refusal(answer):
        return False
    return not has_citations


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return count / total


def _extract_total_tokens(response: Dict[str, Any]) -> int:
    usage = response.get("usage")
    if isinstance(usage, dict):
        total_tokens = usage.get("total_tokens")
        try:
            value = int(total_tokens)
            if value >= 0:
                return value
        except (TypeError, ValueError):
            pass

    fallback = response.get("tokens_generated")
    try:
        value = int(fallback)
        return max(value, 0)
    except (TypeError, ValueError):
        return 0


def _extract_tokens_per_second(response: Dict[str, Any]) -> Optional[float]:
    direct = response.get("tokens_per_second")
    try:
        if direct is not None:
            value = float(direct)
            if value >= 0:
                return value
    except (TypeError, ValueError):
        return None
    return None


def run_regression_eval(
    query_fn: Callable[[str, int], Dict[str, Any]],
    dataset: Optional[List[Dict[str, Any]]] = None,
    variants: Optional[List[Dict[str, str]]] = None,
    top_k: int = 3,
    run_id: Optional[str] = None,
    artifact_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    run_id = run_id or uuid.uuid4().hex
    dataset = dataset or DEFAULT_DATASET
    variants = variants or PROMPT_VARIANTS

    repo_root = Path(__file__).resolve().parents[3]
    artifact_dir = artifact_dir or repo_root / "artifacts" / "eval_runs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_path = artifact_dir / f"regression_{run_id}.jsonl"

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    logger.info(
        "Starting regression eval run_id=%s cases=%s variants=%s output=%s",
        run_id,
        len(dataset),
        len(variants),
        output_path,
    )

    variant_metrics: Dict[str, Dict[str, Any]] = {}
    overall_latencies: List[int] = []
    overall_counts = {"coverage": 0, "refusal": 0, "hallucination": 0}
    total_cases = 0

    with output_path.open("w", encoding="utf-8") as handle:
        for variant in variants:
            name = variant["name"]
            prompt_prefix = variant.get("prompt_prefix", "")
            latencies: List[int] = []
            counts = {"coverage": 0, "refusal": 0, "hallucination": 0}

            logger.info("Evaluating variant=%s", name)
            for case in dataset:
                question = case["question"]
                prompted_question = _apply_prompt(prompt_prefix, question)
                start = time.perf_counter()
                response = query_fn(prompted_question, top_k)
                latency_ms = (time.perf_counter() - start) * 1000.0
                answer = response.get("answer", "")
                citations = response.get("citations", [])
                total_tokens = _extract_total_tokens(response)
                tokens_per_second = _extract_tokens_per_second(response)
                if tokens_per_second is None and latency_ms > 0:
                    tokens_per_second = total_tokens / (latency_ms / 1000.0)

                coverage = bool(citations)
                refusal = _is_refusal(answer)
                hallucination = _is_hallucination(answer, citations)
                eval_pass = coverage and not refusal and not hallucination

                counts["coverage"] += int(coverage)
                counts["refusal"] += int(refusal)
                counts["hallucination"] += int(hallucination)
                latencies.append(int(latency_ms))
                overall_latencies.append(int(latency_ms))

                total_cases += 1
                overall_counts["coverage"] += int(coverage)
                overall_counts["refusal"] += int(refusal)
                overall_counts["hallucination"] += int(hallucination)

                record = {
                    "run_id": run_id,
                    "variant": name,
                    "question_id": case.get("id"),
                    "question": question,
                    "prompted_question": prompted_question,
                    "answer": answer,
                    "num_citations": len(citations),
                    "citation_coverage": coverage,
                    "refusal": refusal,
                    "hallucination": hallucination,
                    "latency_ms": round(latency_ms, 3),
                    "tokens_generated": total_tokens,
                    "tokens_per_second": round(tokens_per_second, 3) if tokens_per_second is not None else None,
                    "eval_pass": eval_pass,
                    "timestamp": created_at,
                }
                handle.write(json.dumps(record) + "\n")

            variant_metrics[name] = {
                "total_cases": len(dataset),
                "citation_coverage_rate": round(_rate(counts["coverage"], len(dataset)), 4),
                "refusal_rate": round(_rate(counts["refusal"], len(dataset)), 4),
                "hallucination_rate": round(_rate(counts["hallucination"], len(dataset)), 4),
                "latency_p50_ms": _nearest_rank(latencies, 0.50),
                "latency_p95_ms": _nearest_rank(latencies, 0.95),
            }

    summary = {
        "run_id": run_id,
        "created_at": created_at,
        "output_file": str(output_path),
        "variants": variant_metrics,
        "overall": {
            "total_cases": total_cases,
            "citation_coverage_rate": round(_rate(overall_counts["coverage"], total_cases), 4),
            "refusal_rate": round(_rate(overall_counts["refusal"], total_cases), 4),
            "hallucination_rate": round(_rate(overall_counts["hallucination"], total_cases), 4),
            "latency_p50_ms": _nearest_rank(overall_latencies, 0.50),
            "latency_p95_ms": _nearest_rank(overall_latencies, 0.95),
        },
    }

    logger.info("Completed regression eval run_id=%s", run_id)
    return summary
