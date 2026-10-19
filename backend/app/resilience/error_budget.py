from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ErrorBudgetResult:
    name: str
    target_availability: float
    total_requests: int
    failed_requests: int
    observed_availability: float
    allowable_failures: int
    budget_consumed_percent: float
    budget_remaining_percent: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def calculate_error_budget(
    total_requests: int,
    failed_requests: int,
    *,
    target_availability: float = 0.99,
    name: str = "CI resilience error budget",
) -> ErrorBudgetResult:
    total = max(0, int(total_requests))
    failed = min(max(0, int(failed_requests)), total)
    target = min(max(float(target_availability), 0.0), 1.0)
    allowable = math.floor(total * (1.0 - target))
    observed = (total - failed) / total if total else 0.0
    consumed = (failed / allowable * 100.0) if allowable else (100.0 if failed else 0.0)
    return ErrorBudgetResult(
        name=name,
        target_availability=target,
        total_requests=total,
        failed_requests=failed,
        observed_availability=round(observed, 6),
        allowable_failures=allowable,
        budget_consumed_percent=round(min(consumed, 100.0), 3),
        budget_remaining_percent=round(max(0.0, 100.0 - consumed), 3),
    )
