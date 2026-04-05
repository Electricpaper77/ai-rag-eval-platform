from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class HPCJobSchema:
    """Lightweight mock schema for HPC-style GPU batch jobs."""

    job_name: str
    gpu_count: int
    memory_required: str
    time_limit: str
    priority: str
    queue: str

    def to_dict(self) -> Dict[str, str | int]:
        return {
            "job_name": self.job_name,
            "gpu_count": self.gpu_count,
            "memory_required": self.memory_required,
            "time_limit": self.time_limit,
            "priority": self.priority,
            "queue": self.queue,
        }


EXAMPLE_HPC_JOB_SCHEMA = HPCJobSchema(
    job_name="eval-benchmark",
    gpu_count=1,
    memory_required="16Gi",
    time_limit="00:30:00",
    priority="normal",
    queue="gpu-standard",
)
