from __future__ import annotations

from app.benchmark import BenchmarkRecorder, sample_record


def test_benchmark_metrics_summary_contains_required_fields():
    recorder = BenchmarkRecorder()
    recorder.record(sample_record("mock-local", "lowest_latency", 40, 120, 0.001))
    recorder.record(sample_record("mock-local", "lowest_latency", 80, 160, 0.002))
    summary = recorder.summary()
    assert summary["p50_latency_ms"] == 60
    assert summary["p95_latency_ms"] > 40
    assert summary["tokens_per_second"] > 0
    assert summary["cost_per_request_usd"] > 0
    assert summary["leaderboard"][0]["ttft_p50_ms"] > 0


def test_benchmark_leaderboard_csv_is_generated(tmp_path):
    recorder = BenchmarkRecorder()
    recorder.record(sample_record("mock-local", "lowest_latency", 40, 120, 0.001))
    recorder.record(sample_record("vllm-a10g", "highest_quality", 65, 180, 0.002))
    path = tmp_path / "benchmark_leaderboard.csv"
    recorder.write_leaderboard(path)
    text = path.read_text(encoding="utf-8")
    assert "backend" in text
    assert "tokens_per_second" in text
    assert "ttft_p50_ms" in text


def test_prometheus_metrics_exposure(client, chat_payload):
    client.post("/v1/chat/completions", json=chat_payload)
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "inference_requests_total" in text
    assert "inference_request_latency_seconds" in text
    assert "inference_time_to_first_token_seconds" in text
    assert "inference_tokens_per_second" in text
    assert "inference_routing_decisions_total" in text


def test_benchmark_artifacts_are_generated(client, chat_payload, tmp_path):
    client.post("/v1/chat/completions", json=chat_payload)
    response = client.get("/benchmark/summary")
    assert response.status_code == 200
    assert (tmp_path / "benchmark_results.json").exists()
    assert (tmp_path / "benchmark_leaderboard.csv").exists()
    assert (tmp_path / "opentelemetry_pipeline.json").exists()
    assert (tmp_path / "routing_decisions.jsonl").exists()
    assert (tmp_path / "evaluation_results.jsonl").exists()
    assert (tmp_path / "otel_traces.jsonl").exists()
    assert (tmp_path / "metrics_sample.txt").exists()


def test_streaming_artifacts_and_metrics_are_generated(client, chat_payload, tmp_path):
    with client.stream("POST", "/v1/chat/completions", json={**chat_payload, "stream": True}) as response:
        assert response.status_code == 200
        _ = "".join(response.iter_text())

    metrics_text = client.get("/metrics").text
    assert "inference_time_to_first_token_seconds" in metrics_text
    assert "inference_tokens_per_second" in metrics_text
    assert (tmp_path / "streaming_results.jsonl").exists()


def test_opentelemetry_pipeline_artifact_documents_export_path(client, tmp_path):
    path = tmp_path / "opentelemetry_pipeline.json"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "otlp_exporter_enabled" in text
    assert "collector_config" in text
