from __future__ import annotations

from dataclasses import dataclass
import os

HARD_MAX_REQUESTS = 50
HARD_MAX_CONCURRENCY = 8
HARD_MAX_RETRIES = 2


@dataclass(frozen=True)
class Profile:
    name: str
    default_requests: int
    default_concurrency: int
    warmups: int
    telemetry_interval_seconds: float


PROFILES = {
    "moderate": Profile("moderate", 10, 1, 0, 1.0),
    "performance": Profile("performance", 50, 1, 3, 0.5),
}


def bounded_int(value: int | None, env_name: str, default: int, maximum: int) -> int:
    raw = value if value is not None else os.getenv(env_name, default)
    try:
        result = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{env_name} must be an integer") from exc
    if not 1 <= result <= maximum:
        raise ValueError(f"{env_name} must be between 1 and {maximum}")
    return result
