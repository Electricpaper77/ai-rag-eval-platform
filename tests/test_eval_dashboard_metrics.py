import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.build_eval_dashboard import summarize_runs


def test_eval_dashboard_metrics_structure() -> None:
    payload = summarize_runs(Path("artifacts/proof"))
    assert "runs" in payload
    assert payload["runs"]

    run = payload["runs"][0]
    assert "p50_latency_ms" in run
    assert "p95_latency_ms" in run
    assert 0.0 <= run["pass_rate"] <= 1.0
    assert "tokens_per_sec_avg" in run
