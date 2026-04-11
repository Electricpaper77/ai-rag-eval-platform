from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from gpu_platform.metrics import record_benchmark_metrics
except Exception:
    def record_benchmark_metrics(model: str, latency_ms: float, tokens_per_second: float, runs: int = 1) -> None:
        return None

DEFAULT_DATASET = "eval/prompts.jsonl"
DEFAULT_OUTPUT = "artifacts/leaderboard/model_benchmark_results.jsonl"
DEFAULT_PROOF = "artifacts/proof/benchmark_run_example.json"

DEFAULT_MODELS = [
    "openai/gpt-4o-mini",
    "mistral-7b-instruct",
    "mock/local-model",
]

MODEL_PRICING_PER_1K_TOKENS = {
    "openai/gpt-4o-mini": 0.0009,
    "mistral-7b-instruct": 0.0003,
    "mock/local-model": 0.0,
}

FACTUAL_KEYWORDS = {
    "what is the capital of france?": ["paris"],
    "who wrote hamlet?": ["shakespeare"],
    "what is the speed of light?": ["299", "3", "m/s"],
}


def _read_dataset(dataset_path: Path) -> list[str]:
    prompts: list[str] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            prompt = str(row.get("prompt") or row.get("input") or row.get("question") or "").strip()
            if prompt:
                prompts.append(prompt)
    return prompts


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(max(int(math.ceil(p * len(ordered))) - 1, 0), len(ordered) - 1)
    return float(ordered[idx])


def _extract_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def _usage_tokens(payload: dict[str, Any]) -> int:
    usage = payload.get("usage") or {}
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return total
    completion = usage.get("completion_tokens")
    prompt = usage.get("prompt_tokens")
    if isinstance(completion, int) and isinstance(prompt, int):
        return completion + prompt
    return 0


def _pass_for_prompt(prompt: str, answer: str) -> bool:
    answer_l = answer.lower()
    expected = FACTUAL_KEYWORDS.get(prompt.strip().lower())
    if expected:
        return all(token in answer_l for token in expected)
    if not answer.strip():
        return False
    if "i don't know" in answer_l or "cannot answer" in answer_l:
        return False
    return True


def _hallucination_for_prompt(prompt: str, answer: str) -> bool:
    answer_l = answer.lower()
    if not answer.strip():
        return True
    if "[citation needed]" in answer_l:
        return True
    expected = FACTUAL_KEYWORDS.get(prompt.strip().lower())
    return bool(expected) and not _pass_for_prompt(prompt, answer)


def _post_chat_completion(base_url: str, model: str, prompt: str, timeout: float) -> tuple[float, dict[str, Any], bool]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise evaluation assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 256,
    }
    req = request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            response_payload = json.loads(resp.read().decode("utf-8"))
            ok = 200 <= resp.status < 300
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
        elapsed_ms = (time.perf_counter() - start) * 1000
        return elapsed_ms, {}, False

    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms, response_payload, ok


def _run_model(base_url: str, model: str, prompts: list[str], timeout: float) -> dict[str, Any]:
    latencies: list[float] = []
    per_request_tps: list[float] = []
    pass_flags: list[float] = []
    hallucination_flags: list[float] = []
    costs: list[float] = []

    for prompt in prompts:
        latency_ms, payload, ok = _post_chat_completion(base_url=base_url, model=model, prompt=prompt, timeout=timeout)
        latencies.append(latency_ms)
        answer = _extract_text(payload) if ok else ""
        total_tokens = _usage_tokens(payload) if ok else 0

        tps = (total_tokens / max(latency_ms / 1000.0, 1e-6)) if total_tokens > 0 else 0.0
        per_request_tps.append(tps)

        passed = _pass_for_prompt(prompt, answer) if ok else False
        hallucinated = _hallucination_for_prompt(prompt, answer) if ok else True
        pass_flags.append(1.0 if passed else 0.0)
        hallucination_flags.append(1.0 if hallucinated else 0.0)

        unit_price = MODEL_PRICING_PER_1K_TOKENS.get(model, 0.0)
        costs.append((total_tokens / 1000.0) * unit_price)

        record_benchmark_metrics(
            model=model,
            latency_ms=latency_ms,
            tokens_per_second=tps,
            runs=1,
        )

    return {
        "model": model,
        "avg_latency_ms": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "p50_latency_ms": round(statistics.median(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(_percentile(latencies, 0.95), 3),
        "tokens_per_second": round(statistics.mean(per_request_tps), 3) if per_request_tps else 0.0,
        "eval_pass_rate": round(statistics.mean(pass_flags), 4) if pass_flags else 0.0,
        "hallucination_rate": round(statistics.mean(hallucination_flags), 4) if hallucination_flags else 0.0,
        "cost_per_request": round(statistics.mean(costs), 6) if costs else 0.0,
        "requests": len(prompts),
    }


def run_benchmark(base_url: str, dataset_path: Path, models: list[str], output_path: Path, proof_path: Path, timeout: float) -> list[dict[str, Any]]:
    prompts = _read_dataset(dataset_path)
    results = [_run_model(base_url=base_url, model=model, prompts=prompts, timeout=timeout) for model in models]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row) + "\n")

    proof_payload = {
        "base_url": base_url,
        "dataset": str(dataset_path),
        "models": models,
        "rows_written": len(results),
        "output_path": str(output_path),
        "created_at_unix": int(time.time()),
    }
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof_payload, indent=2), encoding="utf-8")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-model benchmark against /v1/chat/completions")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--proof-output", default=DEFAULT_PROOF)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    results = run_benchmark(
        base_url=args.base_url,
        dataset_path=Path(args.dataset),
        models=args.models,
        output_path=Path(args.output),
        proof_path=Path(args.proof_output),
        timeout=args.timeout,
    )
    print(json.dumps({"models": len(results), "output": args.output, "proof": args.proof_output}, indent=2))


if __name__ == "__main__":
    main()
