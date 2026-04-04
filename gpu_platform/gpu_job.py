from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class GPUJobSpec:
    job_id: str
    model_name: str
    gpu_count: int
    replicas: int
    container_image: str
    env: Dict[str, str] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "model_name": self.model_name,
            "gpu_count": self.gpu_count,
            "replicas": self.replicas,
            "container_image": self.container_image,
            "env": dict(self.env),
            "resources": dict(self.resources),
        }
