from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class _MockOpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        body = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            "usage": {
                "prompt_tokens": 52,
                "completion_tokens": 128,
                "total_tokens": 180,
            },
        }
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_gpu_metrics_artifacts_contain_required_fields() -> None:
    server = HTTPServer(("127.0.0.1", 0), _MockOpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    jsonl_path = REPO_ROOT / "artifacts" / "proof" / "gpu_benchmark_run.jsonl"
    summary_path = REPO_ROOT / "artifacts" / "proof" / "gpu_summary.json"

    if jsonl_path.exists():
        jsonl_path.unlink()
    if summary_path.exists():
        summary_path.unlink()

    env = os.environ.copy()
    env.update(
        {
            "BASE_URL": f"http://127.0.0.1:{server.server_port}",
            "MODEL_NAME": "mistralai/Mistral-7B-Instruct-v0.2",
            "NUM_REQUESTS": "2",
            "RUNTIME": "vllm",
        }
    )

    try:
        subprocess.run(
            [sys.executable, "scripts/run_gpu_benchmark.py"],
            cwd=REPO_ROOT,
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )
    finally:
        server.shutdown()
        thread.join(timeout=3)

    assert jsonl_path.exists(), "jsonl artifact not created"
    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows, "jsonl artifact empty"

    latest = rows[-1]
    assert "tokens_per_sec" in latest
    assert "latency_ms" in latest
    assert latest["status"] == "success"
