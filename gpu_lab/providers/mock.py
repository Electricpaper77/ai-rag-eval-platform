from __future__ import annotations
import time

class MockProvider:
    mode = "mock"
    def __init__(self, latency_seconds: float = 0.001, behavior: str = "success"):
        self.latency_seconds, self.behavior = latency_seconds, behavior
    def complete(self, prompt: str, model: str) -> dict:
        time.sleep(self.latency_seconds)
        if self.behavior == "timeout": raise TimeoutError("simulated timeout")
        if self.behavior in {"429", "500"}: raise RuntimeError(f"simulated HTTP {self.behavior}")
        if self.behavior == "malformed": return {"malformed": True}
        return {"text": f"mock:{prompt}", "output_tokens": 2, "input_tokens": len(prompt.split())}
