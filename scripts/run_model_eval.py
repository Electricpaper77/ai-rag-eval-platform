from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gpu_platform.model_registry import load_model_registry


def _read_prompts(path: Path) -> list[str]:
    prompts: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            prompt = str(row.get("prompt") or row.get("input") or row.get("question") or "")
            if prompt:
                prompts.append(prompt)
    return prompts


def _deterministic_ratio(key: str) -> float:
    raw = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % 10000
    return raw / 10000.0


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(p * len(ordered)) - 1))
    return float(ordered[idx])


def _evaluate_model(model: dict, prompts: list[str]) -> dict:
    pass_values: list[float] = []
    hallucination_values: list[float] = []
    latencies: list[float] = []
    costs: list[float] = []

    for i, prompt in enumerate(prompts):
        seed = f"{model['id']}:{i}:{prompt[:64]}"
        jitter = _deterministic_ratio(seed)

        pass_values.append(1.0 if jitter <= model["quality_score"] else 0.0)
        hallucination_values.append(1.0 if jitter <= (1.0 - model["quality_score"]) * 0.4 else 0.0)
        latencies.append(model["avg_latency_ms"] * (0.8 + jitter * 0.4))
        output_tokens = 200 + int(300 * jitter)
        costs.append((output_tokens / 1000.0) * model["cost_per_1k_tokens"])

    return {
        "model": model["id"],
        "pass_rate": round(mean(pass_values), 4) if pass_values else 0.0,
        "hallucination_rate": round(mean(hallucination_values), 4) if hallucination_values else 0.0,
        "p95_latency_ms": round(_percentile(latencies, 0.95), 2),
        "cost_per_request": round(mean(costs), 6) if costs else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-model evaluation simulation")
    parser.add_argument("--dataset", default="eval/prompts.jsonl")
    parser.add_argument("--registry", default="config/model_registry.yaml")
    parser.add_argument("--output-dir", default="artifacts/model_eval")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    prompts = _read_prompts(dataset_path)

    models = load_model_registry(Path(args.registry))
    leaderboard = [_evaluate_model(model, prompts) for model in models]
    leaderboard.sort(key=lambda row: (row["pass_rate"], -row["cost_per_request"]), reverse=True)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    leaderboard_path = output_dir / "leaderboard.json"
    leaderboard_path.write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")

    print(json.dumps({"leaderboard_path": str(leaderboard_path), "models": len(leaderboard)}, indent=2))


if __name__ == "__main__":
    main()
