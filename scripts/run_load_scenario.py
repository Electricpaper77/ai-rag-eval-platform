from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from gpu_platform.concurrency_controller import (
    MAX_CONCURRENT_JOBS,
    estimate_queue_latency,
)

OUTPUT_PATH = Path("artifacts/load_test/load_summary.json")
CONCURRENCY_LEVELS = [5, 10, 20]
BASELINE_LATENCY_MS = 140.0
LATENCY_PENALTY_PER_QUEUE_JOB_MS = 22.5


def simulate_load_level(concurrency_level: int) -> dict[str, float | int]:
    queue_depth = max(0, concurrency_level - MAX_CONCURRENT_JOBS)
    queue_delay_estimate = estimate_queue_latency(active_jobs=concurrency_level)
    avg_latency = BASELINE_LATENCY_MS + (queue_depth * LATENCY_PENALTY_PER_QUEUE_JOB_MS)

    return {
        "concurrency_level": concurrency_level,
        "avg_latency": round(avg_latency, 2),
        "queue_delay_estimate": queue_delay_estimate,
    }


def main() -> None:
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": [simulate_load_level(level) for level in CONCURRENCY_LEVELS],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote load simulation artifact to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
