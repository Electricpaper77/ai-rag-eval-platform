from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gpu_platform.observability_analyzer as analyzer


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_analyze_queue_pressure_thresholds() -> None:
    assert analyzer.analyze_queue_pressure({"platform_queue_depth": 0})["queue_pressure_level"] == "low"
    assert analyzer.analyze_queue_pressure({"platform_queue_depth": 5})["queue_pressure_level"] == "low"
    assert analyzer.analyze_queue_pressure({"platform_queue_depth": 6})["queue_pressure_level"] == "moderate"
    assert analyzer.analyze_queue_pressure({"platform_queue_depth": 15})["queue_pressure_level"] == "moderate"
    assert analyzer.analyze_queue_pressure({"platform_queue_depth": 16})["queue_pressure_level"] == "high"


def test_collect_and_generate_platform_health_report(tmp_path: Path, monkeypatch) -> None:
    artifacts_dir = tmp_path / "artifacts" / "platform_jobs"

    _write_jsonl(
        artifacts_dir / "jobs.jsonl",
        [
            {
                "job_id": "job-1",
                "status": "failed",
                "failure_reason": "quota_exceeded,invalid_parallelism_config",
                "retry_count": 2,
            },
            {"job_id": "job-2", "status": "queued", "retry_count": 0},
        ],
    )
    _write_jsonl(
        artifacts_dir / "distributed_jobs.jsonl",
        [
            {
                "job_id": "job-1",
                "topology": {"replicas": 1, "gpu_per_replica": 4},
                "parallelism_config": {"tensor_parallel": 1},
                "total_gpu_requested": 4,
            },
            {
                "job_id": "job-2",
                "topology": {"replicas": 2, "gpu_per_replica": 1},
                "parallelism_config": {"tensor_parallel": 2},
                "total_gpu_requested": 2,
            },
        ],
    )
    _write_jsonl(
        artifacts_dir / "admission_rejections.jsonl",
        [{"job_id": "job-1", "reason_codes": ["quota_exceeded", "queue_full"]}],
    )
    _write_jsonl(
        artifacts_dir / "routing_decisions.jsonl",
        [{"gpu_pool": "throughput_pool"}, {"gpu_pool": "throughput_pool"}, {"gpu_pool": "latency_pool"}],
    )
    _write_jsonl(
        artifacts_dir / "runtime_selections.jsonl",
        [{"runtime": "mock_triton"}, {"runtime": "mock_vllm"}],
    )

    monkeypatch.setattr(analyzer, "PLATFORM_JOB_ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(analyzer, "FAILURE_SUMMARY_FILE", artifacts_dir / "platform_failure_summary.json")
    monkeypatch.setattr(analyzer, "HEALTH_REPORT_FILE", artifacts_dir / "platform_health_report.json")

    metrics = analyzer.collect_platform_metrics(artifacts_dir=artifacts_dir)
    routing = analyzer.analyze_runtime_selection(metrics)
    assert routing["routing_distribution"]["throughput_pool"] == 66.67
    assert routing["routing_distribution"]["distributed_pool"] == 0.0

    parallelism = analyzer.analyze_parallelism_efficiency(metrics)
    assert parallelism["average_replicas"] == 1.5
    assert len(parallelism["inefficient_configurations"]) == 1

    report = analyzer.generate_platform_health_report(metrics)
    assert report["queue_pressure_level"] == "low"
    assert report["failure_summary"]["admission_rejection_reasons"]["quota_exceeded"] == 1

    failure_summary = json.loads((artifacts_dir / "platform_failure_summary.json").read_text(encoding="utf-8"))
    assert failure_summary["failure_reason_frequency"]["invalid_parallelism_config"] == 1

    report_file = json.loads((artifacts_dir / "platform_health_report.json").read_text(encoding="utf-8"))
    assert report_file["runtime_usage_summary"]["runtime_selection_counts"]["mock_triton"] == 1
