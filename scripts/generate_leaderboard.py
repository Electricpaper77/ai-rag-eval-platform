from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_INPUT = "artifacts/leaderboard/model_benchmark_results.jsonl"
DEFAULT_OUTPUT = "artifacts/leaderboard_summary.md"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _as_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def render_markdown(rows: list[dict[str, Any]]) -> str:
    rows = sorted(rows, key=lambda row: (float(row.get("eval_pass_rate", 0.0)), -float(row.get("p95_latency_ms", 0.0))), reverse=True)
    lines = [
        "# Model Benchmark Leaderboard",
        "",
        "| model | p50 latency | p95 latency | tokens/sec | pass rate | hallucination |",
        "|------|-------------|-------------|------------|-----------|--------------|",
    ]

    for row in rows:
        lines.append(
            "| {model} | {p50:.2f} ms | {p95:.2f} ms | {tps:.2f} | {pass_rate} | {hallucination} |".format(
                model=row.get("model", "unknown"),
                p50=float(row.get("p50_latency_ms", row.get("avg_latency_ms", 0.0))),
                p95=float(row.get("p95_latency_ms", 0.0)),
                tps=float(row.get("tokens_per_second", 0.0)),
                pass_rate=_as_percent(row.get("eval_pass_rate", 0.0)),
                hallucination=_as_percent(row.get("hallucination_rate", 0.0)),
            )
        )

    if len(lines) == 4:
        lines.append("| _no data_ | 0.00 ms | 0.00 ms | 0.00 | 0.00% | 0.00% |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate leaderboard markdown from model benchmark JSONL")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = _load_jsonl(Path(args.input))
    markdown = render_markdown(rows)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(json.dumps({"rows": len(rows), "output": str(output_path)}, indent=2))


if __name__ == "__main__":
    main()
