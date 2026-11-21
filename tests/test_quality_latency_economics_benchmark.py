import copy
import json

from scripts.run_quality_latency_economics_benchmark import BENCHMARK, _config_hash, load_workload, quality_non_regression, run, validate_records, validate_workload_parity


def test_benchmark_emits_reproducible_two_config_evidence(tmp_path):
    summary = run(tmp_path, runs_per_config=3, concurrency=2, warmup=1)
    assert summary["benchmark"] == BENCHMARK
    assert summary["mode"] == "offline_simulated"
    assert set(summary["configs"]) == {"baseline", "optimized"}
    assert summary["comparison"]["quality_non_regression"] is True
    assert (tmp_path / "raw_requests.jsonl").read_text().count("\n") == 36
    assert summary["configs"]["baseline"]["request_count"] == 15
    assert summary["configs"]["baseline"]["warmup_requests"] == 3
    assert "requests_per_second" not in summary["configs"]["baseline"]
    assert "serial_equivalent_requests_per_second" in summary["configs"]["baseline"]
    assert summary["integrity_errors"] == []
    assert (tmp_path / "run_manifest.json").exists()
    assert (tmp_path / "baseline_vs_optimized.json").exists()
    assert (tmp_path / "benchmark_report.md").exists()


def test_benchmark_records_quality_safety_and_estimated_cost(tmp_path):
    run(tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "raw_requests.jsonl").read_text().splitlines()]
    assert {row["case_id"] for row in rows} == {"warmup", "grounded-rag", "refusal", "pii", "prompt-injection", "ordinary"}
    assert len({row["record_id"] for row in rows}) == 36
    assert sum(row["warmup"] for row in rows) == 6
    assert all(row["mode"] == "offline_simulated" for row in rows)
    assert all("estimated_cost_usd" in row for row in rows)
    measured = [row for row in rows if not row["warmup"]]
    assert all("pii_leakage" in row and "prompt_injection_resistant" in row for row in measured)


def test_validation_rejects_malformed_duplicate_and_hash_mismatch(tmp_path):
    run(tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "raw_requests.jsonl").read_text().splitlines()]
    broken = copy.deepcopy(rows[0])
    broken.pop("latency_ms")
    broken["record_id"] = rows[1]["record_id"]
    broken["dataset_sha256"] = "bad"
    errors = validate_records([broken], rows[0]["dataset_sha256"], _config_hash())
    assert any("missing fields" in error for error in errors)
    assert any("duplicate" in error for error in validate_records([rows[0], rows[0]], rows[0]["dataset_sha256"], _config_hash()))
    assert any("hash mismatch" in error for error in errors)


def test_validation_rejects_workload_mismatch_and_quality_regression(tmp_path):
    run(tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "raw_requests.jsonl").read_text().splitlines()]
    rows[-1]["case_id"] = "different-workload"
    assert validate_workload_parity(rows) == ["baseline/optimized workload mismatch"]
    workload, _ = load_workload()
    assert len(workload) == 5
    baseline = {"category_qualification": {"grounded-rag": {"qualification_rate": 1.0}}}
    optimized = {"category_qualification": {"grounded-rag": {"qualification_rate": 0.0}}}
    assert quality_non_regression(baseline, optimized) is False


def test_zero_quality_success_has_no_division_or_fabricated_cost(tmp_path):
    run(tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "raw_requests.jsonl").read_text().splitlines() if '"warmup": false' in line]
    for row in rows:
        row["quality_pass"] = False
    from scripts.run_quality_latency_economics_benchmark import _aggregate
    result = _aggregate(rows, runs=3, concurrency=2, warmups=0)
    assert result["quality_qualified_requests"] == 0
    assert result["estimated_cost_per_quality_success_usd"] is None
    assert result["zero_quality_success_status"] == "unavailable_no_quality_success"
