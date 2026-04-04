import json
import subprocess
import sys
from pathlib import Path


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_threshold_gate_fails_with_reason(tmp_path: Path) -> None:
    config = tmp_path / "eval_thresholds.yaml"
    config.write_text(
        "\n".join(
            [
                "min_pass_rate: 0.8",
                "max_p95_latency_ms: 1500",
                "min_tokens_per_sec: 5",
            ]
        ),
        encoding="utf-8",
    )

    artifact = tmp_path / "eval_1.jsonl"
    _write_jsonl(
        artifact,
        [
            {"eval_pass": True, "latency_ms": 1000, "tokens_generated": 10},
            {"eval_pass": True, "latency_ms": 1800, "tokens_generated": 10},
            {"eval_pass": False, "latency_ms": 1800, "tokens_generated": 10},
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_eval_thresholds.py",
            "--config",
            str(config),
            "--artifact",
            str(artifact),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "FAIL: p95 latency" in result.stdout
    assert "exceeds threshold 1500ms" in result.stdout


def test_threshold_gate_passes(tmp_path: Path) -> None:
    config = tmp_path / "eval_thresholds.yaml"
    config.write_text(
        "\n".join(
            [
                "min_pass_rate: 0.5",
                "max_p95_latency_ms: 2000",
                "min_tokens_per_sec: 4",
            ]
        ),
        encoding="utf-8",
    )

    artifact = tmp_path / "eval_2.jsonl"
    _write_jsonl(
        artifact,
        [
            {"eval_pass": True, "latency_ms": 900, "tokens_generated": 10},
            {"eval_pass": False, "latency_ms": 1200, "tokens_generated": 8},
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_eval_thresholds.py",
            "--config",
            str(config),
            "--artifact",
            str(artifact),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("PASS:")
