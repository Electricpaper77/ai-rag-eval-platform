from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SHADOW_SUMMARY_PATH = Path("artifacts/proof/shadow_eval_summary.json")


def record_shadow_result(result: dict[str, Any], summary_path: Path | None = None) -> dict[str, Any]:
    path = summary_path or SHADOW_SUMMARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    history: list[dict[str, Any]] = []
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        history = payload.get("comparisons", [])

    history.append(result)

    avg_latency_delta = 0.0
    if history:
        avg_latency_delta = sum(
            float(item["shadow_latency_ms"]) - float(item["selected_latency_ms"]) for item in history
        ) / len(history)

    summary = {
        "total_comparisons": len(history),
        "avg_latency_delta_ms": round(avg_latency_delta, 2),
        "comparisons": history,
    }

    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
