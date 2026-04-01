from __future__ import annotations


class BaseRuntime:
    """Common runtime interface so evaluation can switch LLM backends behind one API."""

    def generate(self, prompt: str, **kwargs) -> dict:
        raise NotImplementedError
