from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseRuntime(ABC):
    """Async runtime contract for OpenAI-compatible chat generation."""

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> Dict[str, Any]:
        raise NotImplementedError
