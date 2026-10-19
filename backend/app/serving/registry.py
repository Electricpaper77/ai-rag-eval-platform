from __future__ import annotations

from typing import Any

from .models import ModelRecord


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[tuple[str, str], ModelRecord] = {}

    def register(self, record: ModelRecord) -> ModelRecord:
        self._models[(record.name, record.version)] = record
        return record

    def get(self, name: str, version: str) -> ModelRecord | None:
        return self._models.get((name, version))

    def all(self) -> list[ModelRecord]:
        return list(self._models.values())

    def snapshot(self) -> list[dict[str, Any]]:
        return [record.as_dict() for record in self.all()]

    def clear_metrics(self) -> None:
        for record in self._models.values():
            record.latency_p95_ms = 0.0
            record.error_rate = 0.0
            record.request_count = 0
            record.error_count = 0
            record.latency_samples_ms.clear()
