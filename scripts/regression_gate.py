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

    if total == 0:
        raise ValueError("No evaluation rows found in JSONL file.")

    pass_rate = passes / total
    avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0
    hallucination_rate = hallucinations / total

    return {
        "pass_rate": pass_rate,
        "avg_latency_ms": avg_latency_ms,
        "hallucination_rate": hallucination_rate,
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
        "status": status,
    }

    print(json.dumps(summary, indent=2))

    if status == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
