from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

MODEL_REGISTRY_PATH = Path("config/model_registry.yaml")


def load_model_registry(path: Path | None = None) -> list[dict[str, Any]]:
    registry_path = path or MODEL_REGISTRY_PATH
    if not registry_path.exists():
        return []

    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    models = payload.get("models", [])
    if not isinstance(models, list):
        return []

    normalized: list[dict[str, Any]] = []
    for row in models:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        normalized.append(
            {
                "id": str(row.get("id")),
                "provider": str(row.get("provider", "unknown")),
                "quality_score": float(row.get("quality_score", 0.0)),
                "avg_latency_ms": float(row.get("avg_latency_ms", 0.0)),
                "cost_per_1k_tokens": float(row.get("cost_per_1k_tokens", 0.0)),
            }
        )
    return normalized
