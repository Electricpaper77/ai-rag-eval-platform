from __future__ import annotations

import random
import time
from typing import Any, Dict

from .gpu_job import GPUJobSpec


def simulate_job_health(job: GPUJobSpec, status: str) -> Dict[str, Any]:
    startup_latency_ms = int(300 + (job.gpu_count * 100) + random.randint(0, 150))
    readiness_status = status in {"running", "completed"}
    gpu_allocated = status in {"running", "completed"}

    return {
        "timestamp": int(time.time()),
        "startup_latency_ms": startup_latency_ms,
        "readiness_status": readiness_status,
        "gpu_allocated": gpu_allocated,
    }
