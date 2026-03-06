import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate inference cost per request and evaluation run."
    )
    parser.add_argument(
        "--avg_tokens_per_request",
        type=float,
        required=True,
        help="Average number of tokens used per request.",
    )
    parser.add_argument(
        "--price_per_1k_tokens",
        type=float,
        required=True,
        help="Price in USD per 1,000 tokens.",
    )
    parser.add_argument(
        "--requests_per_eval_run",
        type=int,
        required=True,
        help="Number of requests executed in one evaluation run.",
    )
    parser.add_argument(
        "--output",
        default="docs/artifacts/cost_analysis.json",
        help="Output JSON path (default: docs/artifacts/cost_analysis.json).",
    )
    return parser.parse_args()


def compute_costs(
    avg_tokens_per_request: float, price_per_1k_tokens: float, requests_per_eval_run: int
) -> dict:
    cost_per_request = (avg_tokens_per_request / 1000.0) * price_per_1k_tokens
    cost_per_1000_requests = cost_per_request * 1000
    cost_per_eval_run = cost_per_request * requests_per_eval_run

    return {
        "avg_tokens_per_request": avg_tokens_per_request,
        "price_per_1k_tokens": price_per_1k_tokens,
        "requests_per_eval_run": requests_per_eval_run,
        "cost_per_request": round(cost_per_request, 6),
        "cost_per_1000_requests": round(cost_per_1000_requests, 2),
        "cost_per_eval_run": round(cost_per_eval_run, 6),
    }


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cost_report = compute_costs(
        avg_tokens_per_request=args.avg_tokens_per_request,
        price_per_1k_tokens=args.price_per_1k_tokens,
        requests_per_eval_run=args.requests_per_eval_run,
    )

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(cost_report, f, indent=2)

    print(f"Wrote cost analysis to {output_path}")


if __name__ == "__main__":
    main()
