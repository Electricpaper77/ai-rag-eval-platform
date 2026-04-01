from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ..routing import DEFAULT_ROUTER, MultiModelRouter


def compare_routed_models(
    prompt: str,
    models: Iterable[str],
    router: MultiModelRouter = DEFAULT_ROUTER,
) -> Dict[str, Any]:
    """Generate a side-by-side comparison for routed model outputs.

    Output rows intentionally include the same core keys used in JSONL eval logs
    (`prompt`, `answer`, `latency_ms`, `tokens_generated`) for compatibility.
    """
    normalized_prompt = (prompt or "").strip()
    rows: List[Dict[str, Any]] = []

    for requested_model in models:
        routed_model, result = router.generate(requested_model, normalized_prompt)
        row = {
            "prompt": normalized_prompt,
            "requested_model": requested_model,
            "model": routed_model,
            "answer": result.response,
            "response": result.response,
            "latency_ms": round(float(result.latency_ms or 0.0), 3),
            "tokens_generated": int(result.tokens_generated or 0),
        }
        rows.append(row)

    return {
        "prompt": normalized_prompt,
        "comparisons": rows,
    }
