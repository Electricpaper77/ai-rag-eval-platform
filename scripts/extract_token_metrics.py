#!/usr/bin/env python3
"""Utility helpers for extracting token usage from OpenAI-compatible responses."""

from __future__ import annotations

from typing import Any, Mapping


def extract_completion_tokens(response: Mapping[str, Any]) -> int:
    """Return completion token count from an OpenAI-compatible JSON payload."""

    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return 0

    completion_tokens = usage.get("completion_tokens", 0)
    try:
        return int(completion_tokens)
    except (TypeError, ValueError):
        return 0


__all__ = ["extract_completion_tokens"]
