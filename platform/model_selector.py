from __future__ import annotations

from typing import Any

from gpu_platform.model_selector import select_best_model as _select_best_model


def select_best_model(
    quality_weight: float = 0.5,
    latency_weight: float = 0.3,
    cost_weight: float = 0.2,
) -> dict[str, Any]:
    return _select_best_model(
        quality_weight=quality_weight,
        latency_weight=latency_weight,
        cost_weight=cost_weight,
    )
