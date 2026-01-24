import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def log_run(
    question: str,
    top_k: int,
    answer: str,
    citations: List[Dict[str, Any]],
    latency_ms: int,
) -> None:
    """Append a single run row to runs.csv.

    Cloud Run filesystem is read-only except /tmp, so write to:
    - RESULTS_DIR env var (if set), else
    - /tmp/results
    """
    results_dir = Path(os.getenv("RESULTS_DIR", "/tmp/results"))
    results_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "runs.csv"
    file_exists = csv_path.exists()

    answer_length = len(answer or "")
    citations_count = len(citations or [])

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)

        if not file_exists:
            w.writerow(
                [
                    "timestamp",
                    "question",
                    "top_k",
                    "answer_length",
                    "citations_count",
                    "latency_ms",
                ]
            )

        w.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                question,
                top_k,
                answer_length,
                citations_count,
                latency_ms,
            ]
        )
