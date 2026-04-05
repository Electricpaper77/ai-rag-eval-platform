from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app import router as runtime_router
from runtimes.triton_runtime import TritonRuntime
import scripts.run_triton_benchmark as run_triton_benchmark


def test_router_registers_triton_runtime() -> None:
    assert "triton" in runtime_router.ROUTER


def test_triton_payload_transform_shape() -> None:
    runtime = TritonRuntime(base_url="http://triton:8000", model_name="demo-model")
    payload = runtime._to_triton_payload(
        {
            "model": "demo-model",
            "messages": [
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": "hello"},
            ],
            "max_tokens": 64,
            "temperature": 0.1,
        }
    )

    assert payload["inputs"][0]["name"] == "PROMPT"
    assert payload["inputs"][0]["datatype"] == "BYTES"
    assert payload["parameters"]["max_tokens"] == 64


def test_run_triton_benchmark_writes_expected_artifacts(tmp_path: Path) -> None:
    summary = run_triton_benchmark.run_triton_benchmark(output_dir=tmp_path, prompts=["one", "two"])

    assert (tmp_path / "benchmark_summary.json").exists()
    assert (tmp_path / "latency_results.json").exists()
    assert (tmp_path / "throughput_results.json").exists()

    loaded_summary = json.loads((tmp_path / "benchmark_summary.json").read_text(encoding="utf-8"))
    assert loaded_summary["runtime"] == "triton"
    assert loaded_summary["total_requests"] == 2
    assert summary["runtime"] == "triton"
