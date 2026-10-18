"""Run the bounded AgentTrust regression evaluator for the Gate 2 benchmark Job."""
from pathlib import Path
import os
from backend.app.eval.regression import run_regression_eval


def main() -> int:
    artifact_dir = Path(os.environ.get("GATE2_ARTIFACT_DIR", "/tmp/eval_runs"))
    result = run_regression_eval(
        lambda question, _top_k: {"answer": question, "citations": ["local"], "usage": {"total_tokens": 1}},
        run_id="gate2-benchmark",
        artifact_dir=artifact_dir,
    )
    artifact = artifact_dir / "regression_gate2-benchmark.jsonl"
    if not artifact.exists():
        raise RuntimeError(f"benchmark artifact was not created: {artifact}")
    print(result["overall"])
    print(f"artifact={artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
