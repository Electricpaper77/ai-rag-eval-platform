from __future__ import annotations
from typing import Protocol

class Provider(Protocol):
    mode: str
    def complete(self, prompt: str, model: str) -> dict: ...
