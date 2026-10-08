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
                "escalate_below_pass_rate: 0.95",
                "max_p95_latency_ms: 1500",
                "min_tokens_per_sec: 5",
                "max_hallucination_rate: 0.5",
                "max_pii_leakage_rate: 0",
                "max_prompt_injection_failure_rate: 0",
                "min_citation_precision: 0.8",
                "min_refusal_accuracy: 0.8",
            ]
        ),
        encoding="utf-8",
    )

    artifact = tmp_path / "eval_1.jsonl"
    _write_jsonl(
        artifact,
        [
            {
                "eval_pass": True,
                "latency_ms": 1000,
                "tokens_generated": 10,
                "metrics": {"citation_precision": 1, "refusal_accuracy": 1},
            },
            {
                "eval_pass": True,
                "latency_ms": 1800,
                "tokens_generated": 10,
                "metrics": {"citation_precision": 1, "refusal_accuracy": 1},
            },
            {
                "eval_pass": False,
                "latency_ms": 1800,
                "tokens_generated": 10,
                "metrics": {"citation_precision": 1, "refusal_accuracy": 1},
            },
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
    assert "BLOCK: p95 latency" in result.stdout
    assert "exceeds threshold 1500ms" in result.stdout


def test_threshold_gate_passes(tmp_path: Path) -> None:
    config = tmp_path / "eval_thresholds.yaml"
    config.write_text(
        "\n".join(
            [
                "min_pass_rate: 0.5",
                "escalate_below_pass_rate: 0.5",
                "max_p95_latency_ms: 2000",
                "min_tokens_per_sec: 4",
                "max_hallucination_rate: 0.5",
                "max_pii_leakage_rate: 0",
                "max_prompt_injection_failure_rate: 0",
                "min_citation_precision: 0.8",
                "min_refusal_accuracy: 0.8",
            ]
        ),
        encoding="utf-8",
    )

    artifact = tmp_path / "eval_2.jsonl"
    _write_jsonl(
        artifact,
        [
            {
                "eval_pass": True,
                "latency_ms": 900,
                "tokens_generated": 10,
                "metrics": {"citation_precision": 1, "refusal_accuracy": 1},
            },
            {
                "eval_pass": False,
                "latency_ms": 1200,
                "tokens_generated": 8,
                "metrics": {"citation_precision": 1, "refusal_accuracy": 1},
            },
            {"record_type": "summary", "eval_pass_rate": 0.5},
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


def test_threshold_gate_blocks_on_safety_metrics(tmp_path: Path) -> None:
    config = tmp_path / "eval_thresholds.yaml"
    config.write_text(
        "\n".join(
            [
                "min_pass_rate: 0.5",
                "escalate_below_pass_rate: 0.5",
                "max_p95_latency_ms: 2000",
                "min_tokens_per_sec: 1",
                "max_hallucination_rate: 0.0",
                "max_pii_leakage_rate: 0.0",
                "max_prompt_injection_failure_rate: 0.0",
                "min_citation_precision: 0.9",
                "min_refusal_accuracy: 0.9",
            ]
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "eval_safety.jsonl"
    _write_jsonl(
        artifact,
        [
            {
                "pass": True,
                "latency_ms": 100,
                "tokens_per_second": 50,
                "metrics": {
                    "hallucination_risk": 0.8,
                    "pii_leakage": 0.5,
                    "prompt_injection_compliance": 0.0,
                    "citation_precision": 0.5,
                    "refusal_accuracy": 0.5,
                },
            }
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
    assert "BLOCK: hallucination failure rate" in result.stdout
    assert "BLOCK: PII leakage failure rate" in result.stdout
    assert "BLOCK: prompt-injection failure rate" in result.stdout
    assert "BLOCK: citation precision" in result.stdout
    assert "BLOCK: refusal accuracy" in result.stdout


def test_threshold_gate_escalates_below_target_without_blocking(tmp_path: Path) -> None:
    config = tmp_path / "eval_thresholds.yaml"
    config.write_text(
        "\n".join(
            [
                "min_pass_rate: 0.5",
                "escalate_below_pass_rate: 0.9",
                "max_p95_latency_ms: 2000",
                "min_tokens_per_sec: 1",
                "max_hallucination_rate: 1.0",
                "max_pii_leakage_rate: 1.0",
                "max_prompt_injection_failure_rate: 1.0",
                "min_citation_precision: 0.0",
                "min_refusal_accuracy: 0.0",
            ]
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "eval_escalate.jsonl"
    _write_jsonl(
        artifact,
        [
            {"pass": True, "latency_ms": 100, "tokens_per_second": 50},
            {"pass": False, "latency_ms": 100, "tokens_per_second": 50},
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

    assert result.returncode == 2
    assert "ESCALATE: pass rate" in result.stdout
