from __future__ import annotations

import asyncio

from backend.runtimes.mock_runtime import MockRuntime


def test_runtime_is_deterministic_for_same_input():
    runtime = MockRuntime()

    async def _run_once():
        return await runtime.generate(
            messages=[
                {"role": "system", "content": "You are deterministic."},
                {"role": "user", "content": "repeatable test"},
            ],
            max_tokens=128,
            temperature=0.7,
            model="mock-llm",
        )

    r1 = asyncio.run(_run_once())
    r2 = asyncio.run(_run_once())

    assert r1["choices"][0]["message"]["content"] == r2["choices"][0]["message"]["content"]
    assert r1["usage"] == r2["usage"]
