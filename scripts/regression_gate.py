import argparse
import json
from pathlib import Path

PASS_RATE_THRESHOLD = 0.80
AVG_LATENCY_MS_THRESHOLD = 2000


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "passed"}
    return False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Gate evaluation results by pass-rate and average latency."
    )
    parser.add_argument("jsonl_path", help="Path to evaluation JSONL file")
    return parser.parse_args()


def load_metrics(jsonl_path: Path):
    total = 0
    passes = 0
    hallucinations = 0
    latencies = []
    token_counts = []
    tokens_per_second = []

    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            row = json.loads(line)
            total += 1

            passed = _to_bool(row.get("eval_pass", row.get("pass", row.get("passed", False))))
            if passed:
                passes += 1

            hallucinated = _to_bool(
                row.get("hallucination", row.get("hallucination_flag", row.get("hallucinated", row.get("is_hallucination", False))))
            )
            if hallucinated:
                hallucinations += 1

            latency = row.get("latency_ms")
            if latency is not None:
                latencies.append(float(latency))

            tokens_generated = row.get("tokens_generated")
            if tokens_generated is not None:
                try:
                    token_counts.append(int(tokens_generated))
                except (TypeError, ValueError):
                    pass

            tps = row.get("tokens_per_second")
            if tps is not None:
                try:
                    tokens_per_second.append(float(tps))
                except (TypeError, ValueError):
                    pass
            elif latency is not None and tokens_generated is not None:
                try:
                    latency_value = float(latency)
                    token_value = float(tokens_generated)
                except (TypeError, ValueError):
                    latency_value = 0.0
                    token_value = 0.0
                if latency_value > 0:
                    tokens_per_second.append(token_value / (latency_value / 1000.0))

    if total == 0:
        raise ValueError("No evaluation rows found in JSONL file.")

    pass_rate = passes / total
    avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0
    hallucination_rate = hallucinations / total
    avg_tokens_generated = sum(token_counts) / len(token_counts) if token_counts else 0.0
    avg_tokens_per_second = sum(tokens_per_second) / len(tokens_per_second) if tokens_per_second else 0.0

    return {
        "pass_rate": pass_rate,
        "avg_latency_ms": avg_latency_ms,
        "hallucination_rate": hallucination_rate,
        "avg_tokens_generated": avg_tokens_generated,
        "avg_tokens_per_second": avg_tokens_per_second,
    }


def main():
    args = parse_args()
    jsonl_path = Path(args.jsonl_path)

    metrics = load_metrics(jsonl_path)

    status = "PASS"
    if metrics["pass_rate"] < PASS_RATE_THRESHOLD or metrics["avg_latency_ms"] > AVG_LATENCY_MS_THRESHOLD:
        status = "FAIL"

    summary = {
        "pass_rate": metrics["pass_rate"],
        "avg_latency_ms": metrics["avg_latency_ms"],
        "avg_tokens_generated": metrics["avg_tokens_generated"],
        "avg_tokens_per_second": metrics["avg_tokens_per_second"],
        "status": status,
    }

    print(json.dumps(summary, indent=2))

    if status == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
