from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_generate_leaderboard_from_jsonl(tmp_path: Path) -> None:
    results_path = tmp_path / "model_benchmark_results.jsonl"
    results_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "model": "openai/gpt-4o-mini",
                        "p50_latency_ms": 220,
                        "p95_latency_ms": 480,
                        "tokens_per_second": 70,
                        "eval_pass_rate": 0.92,
                        "hallucination_rate": 0.03,
                    }
                ),
                json.dumps(
                    {
                        "model": "mock/local-model",
                        "p50_latency_ms": 20,
                        "p95_latency_ms": 40,
                        "tokens_per_second": 130,
                        "eval_pass_rate": 0.75,
                        "hallucination_rate": 0.10,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    output_md = tmp_path / "leaderboard_summary.md"
    cmd = [
        sys.executable,
        "scripts/generate_leaderboard.py",
        "--input",
        str(results_path),
        "--output",
        str(output_md),
    ]
    subprocess.run(cmd, check=True)

    markdown = output_md.read_text(encoding="utf-8")
    assert "| model | p50 latency | p95 latency | tokens/sec | pass rate | hallucination |" in markdown
    assert "openai/gpt-4o-mini" in markdown
    assert "92.00%" in markdown


def test_run_model_benchmark_writes_artifacts(tmp_path: Path) -> None:
    dataset = tmp_path / "prompts.jsonl"
    dataset.write_text("\n".join([json.dumps({"prompt": "Who wrote Hamlet?"}), json.dumps({"prompt": "What is AI?"})]), encoding="utf-8")

    out_jsonl = tmp_path / "leaderboard" / "model_benchmark_results.jsonl"
    proof_json = tmp_path / "proof" / "benchmark_run_example.json"

    cmd = [
        sys.executable,
        "scripts/run_model_benchmark.py",
        "--base-url",
        "http://127.0.0.1:9",
        "--dataset",
        str(dataset),
        "--output",
        str(out_jsonl),
        "--proof-output",
        str(proof_json),
        "--models",
        "mock/local-model",
    ]
    subprocess.run(cmd, check=True)

    rows = [json.loads(line) for line in out_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["model"] == "mock/local-model"
    assert "eval_pass_rate" in rows[0]
    assert proof_json.exists()
