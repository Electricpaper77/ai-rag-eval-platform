#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

import requests
from fastapi import FastAPI


@dataclass
class LocalServerManager:
    host: str = "127.0.0.1"
    port: int = 8000
    timeout_s: float = 20.0
    poll_interval_s: float = 0.5
    use_mock_runtime: bool = False
    process: subprocess.Popen[str] | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def is_healthy(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=1.5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def wait_until_ready(self) -> bool:
        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            if self.is_healthy():
                return True
            time.sleep(self.poll_interval_s)
        return False

    def start(self) -> bool:
        if self.is_healthy():
            return True
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "scripts.local_server:app",
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--log-level",
            "error",
        ]
        env = dict(os.environ)
        if self.use_mock_runtime:
            env["GPU_BENCHMARK_USE_MOCK_RUNTIME"] = "1"
        self.process = subprocess.Popen(cmd, env=env)
        return self.wait_until_ready()

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def _deterministic_latency_ms(quality_tier: str) -> float:
    normalized = quality_tier.strip().lower()
    if normalized == "fast":
        return 350.0
    if normalized == "high_quality":
        return 1200.0
    return 650.0


def _runtime_mode() -> str:
    forced_mock = os.getenv("GPU_BENCHMARK_USE_MOCK_RUNTIME", "0") == "1"
    gpu_available = bool(os.getenv("CUDA_VISIBLE_DEVICES", "").strip())
    return "mock" if forced_mock or not gpu_available else "gpu"


def create_app() -> FastAPI:
    fastapi_app = FastAPI(title="GPU Benchmark Local Server")

    @fastapi_app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "runtime": _runtime_mode()}

    @fastapi_app.post("/v1/chat/completions")
    async def chat_completions(payload: dict[str, Any]) -> dict[str, Any]:
        quality_tier = str(payload.get("quality_tier", "balanced"))
        latency_ms = _deterministic_latency_ms(quality_tier)
        time.sleep(latency_ms / 1000.0)
        prompt_tokens = 8
        completion_tokens = 32
        total_tokens = prompt_tokens + completion_tokens
        return {
            "id": "chatcmpl-benchmark",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", "benchmark-local"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "benchmark-response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "latency_ms": latency_ms,
            "runtime": _runtime_mode(),
        }

    return fastapi_app


app = create_app()


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run local FastAPI server for benchmark")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--use-mock-runtime", action="store_true")
    args = parser.parse_args()

    if args.use_mock_runtime:
        os.environ["GPU_BENCHMARK_USE_MOCK_RUNTIME"] = "1"

    import uvicorn

    def _shutdown_handler(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _shutdown_handler)
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="error")
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
