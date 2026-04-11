from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gpu_platform.model_policy as model_policy


def test_select_model_balances_latency_quality_and_cost(tmp_path: Path, monkeypatch) -> None:
    benchmarks = tmp_path / "model_benchmarks.json"
    decisions = tmp_path / "model_selection_decisions.jsonl"
    benchmarks.write_text(
        json.dumps(
            {
                "slow_hq": {
                    "p50_latency": 650,
                    "quality_score": 0.96,
                    "cost_per_1k_tokens": 0.01,
                },
                "balanced": {
                    "p50_latency": 320,
                    "quality_score": 0.9,
                    "cost_per_1k_tokens": 0.003,
                },
                "cheap_fast": {
                    "p50_latency": 220,
                    "quality_score": 0.72,
                    "cost_per_1k_tokens": 0.001,
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(model_policy, "MODEL_BENCHMARKS_PATH", benchmarks)
    monkeypatch.setattr(model_policy, "MODEL_SELECTION_DECISIONS_PATH", decisions)

    decision = model_policy.select_model(latency_budget_ms=700, quality_tier="balanced", cost_budget=0.01)

    assert decision["selected_model"] == "balanced"
    assert decisions.exists()
    rows = [json.loads(line) for line in decisions.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["selected_model"] == "balanced"


def test_select_model_filters_on_quality_tier(tmp_path: Path, monkeypatch) -> None:
    benchmarks = tmp_path / "model_benchmarks.json"
    benchmarks.write_text(
        json.dumps(
            {
                "premium_a": {"p50_latency": 460, "quality_score": 0.91, "cost_per_1k_tokens": 0.007},
                "premium_b": {"p50_latency": 300, "quality_score": 0.8, "cost_per_1k_tokens": 0.002},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_policy, "MODEL_BENCHMARKS_PATH", benchmarks)
    monkeypatch.setattr(model_policy, "MODEL_SELECTION_DECISIONS_PATH", tmp_path / "decisions.jsonl")

    decision = model_policy.select_model(latency_budget_ms=500, quality_tier="premium", cost_budget=0.01)

    assert decision["selected_model"] == "premium_a"
