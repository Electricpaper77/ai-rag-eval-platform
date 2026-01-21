import csv
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
    """
    Append a single run row to results/runs.csv at the project root.
    This file is a runtime artifact and should be gitignored.
    """
    root = Path(__file__).resolve().parents[2]  # .../backend/app -> project root
    results_dir = root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "runs.csv"
    file_exists = csv_path.exists()

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)

        if not file_exists:
            w.writerow(["timestamp", "question", "top_k", "answer_length", "num_citations", "latency_ms"])

        w.writerow([
            datetime.now(timezone.utc).isoformat(),
            question,
            top_k,
            len((answer or "").split()),
            len(citations or []),
            latency_ms,
        ])
