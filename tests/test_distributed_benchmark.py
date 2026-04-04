from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app.main import app
import gpu_platform.benchmark_summary as benchmark_summary
import scripts.run_distributed_benchmark as distributed_benchmark


class _MockPlatformHandler(BaseHTTPRequestHandler):
    jobs: dict[str, int] = {}

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/platform/jobs":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        job_id = payload["job_id"]
        self.__class__.jobs[job_id] = 0

        response = {
            "job_id": job_id,
            "status": "pending",
            "gpu_count": payload["gpu_count"],
            "replicas": payload["replicas"],
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if not self.path.startswith("/platform/jobs/"):
            self.send_response(404)
            self.end_headers()
            return

        job_id = self.path.rsplit("/", 1)[-1]
        polls = self.__class__.jobs.get(job_id, 0) + 1
        self.__class__.jobs[job_id] = polls

        status = "completed" if polls >= 2 else "running"
        response = {"job_id": job_id, "status": status}
        body = json.dumps(response).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_distributed_benchmark_matrix_and_summary(tmp_path: Path) -> None:
    server = HTTPServer(("127.0.0.1", 0), _MockPlatformHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    proof_dir = tmp_path / "proof"
    summary_path = proof_dir / "distributed_benchmark_summary.json"

    config_path = tmp_path / "benchmark_matrix.yaml"
    config_path.write_text(
        """
models:
  - mistralai/Mistral-7B-Instruct-v0.2
  - meta-llama/Llama-2-7b-chat-hf
batch_sizes:
  - 1
gpu_counts:
  - 1
  - 2
""".strip()
        + "\n",
        encoding="utf-8",
    )

    try:
        summary = distributed_benchmark.run_distributed_benchmark(
            base_url=f"http://127.0.0.1:{server.server_port}",
            config_path=config_path,
            proof_dir=proof_dir,
            summary_path=summary_path,
            poll_interval_s=0.01,
            timeout_s=5,
        )
    finally:
        server.shutdown()
        thread.join(timeout=3)

    assert len(summary["runs"]) == 4
    assert summary_path.exists()

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["runs"]
    first = payload["runs"][0]
    assert "p95_latency_ms" in first
    assert "tokens_per_sec" in first


def test_platform_benchmark_summary_endpoint(tmp_path: Path, monkeypatch) -> None:
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)

    summary_file = proof_dir / "distributed_benchmark_summary.json"
    expected = {
        "runs": [
            {
                "run_id": "distributed-benchmark-001",
                "model": "mistralai/Mistral-7B-Instruct-v0.2",
                "gpu_count": 1,
                "batch_size": 1,
                "p95_latency_ms": 980,
                "tokens_per_sec": 42,
            }
        ]
    }
    summary_file.write_text(json.dumps(expected), encoding="utf-8")

    monkeypatch.setattr(benchmark_summary, "SUMMARY_PATH", summary_file)

    client = TestClient(app)
    response = client.get("/platform/benchmark-summary")

    assert response.status_code == 200
    assert response.json() == expected
