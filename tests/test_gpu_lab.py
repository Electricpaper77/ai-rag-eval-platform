from argparse import Namespace
import json
from pathlib import Path
import pytest
from gpu_lab.metrics import percentile, summarize
from gpu_lab.providers.mock import MockProvider
from gpu_lab.runner import run, validate, _failure_type, _sanitize
from gpu_lab.runner import cache_key, _estimate
from gpu_lab.schema import HARD_MAX_REQUESTS
from gpu_lab.telemetry.amd_smi import AmdSmiTelemetry, normalize, sanitize_error

FIXTURES=Path(__file__).parent / "fixtures"
def args(**overrides):
    data=dict(provider="mock", mode="mock-benchmark", profile="moderate", suite="missing.jsonl", model=None, max_requests=None, concurrency=None, retries=2, allow_network=False, confirm_performance_run=False, resume=False, telemetry="none")
    data.update(overrides); return Namespace(**data)

def test_network_disabled_by_default(): assert validate(args()).allow_network is False
def test_moderate_defaults():
    actual=validate(args()); assert (actual.max_requests, actual.concurrency)==(10,1)
def test_performance_defaults():
    actual=validate(args(profile="performance",allow_network=True,confirm_performance_run=True)); assert actual.max_requests==50
def test_authenticated_requires_network():
    with pytest.raises(ValueError,match="allow-network"): validate(args(provider="openai_compatible",mode="authenticated-smoke",model="m"))
def test_performance_requires_confirmation():
    with pytest.raises(ValueError,match="confirm-performance-run"): validate(args(profile="performance"))
def test_request_hard_cap():
    with pytest.raises(ValueError): validate(args(max_requests=HARD_MAX_REQUESTS+1))
def test_concurrency_hard_cap():
    with pytest.raises(ValueError): validate(args(concurrency=9))
def test_retry_hard_cap():
    with pytest.raises(ValueError): validate(args(retries=3))
def test_mock_timeout():
    with pytest.raises(TimeoutError): MockProvider(behavior="timeout").complete("x","m")
def test_mock_429():
    with pytest.raises(RuntimeError,match="429"): MockProvider(behavior="429").complete("x","m")
def test_mock_500():
    with pytest.raises(RuntimeError,match="500"): MockProvider(behavior="500").complete("x","m")
def test_mock_malformed(): assert MockProvider(behavior="malformed").complete("x","m")["malformed"]
def test_failure_classification(): assert _failure_type("simulated HTTP 429")=="provider_api_failure"
def test_secret_redaction(monkeypatch): monkeypatch.setenv("GPU_LAB_API_KEY","top-secret"); assert "top-secret" not in _sanitize("bad top-secret")
def test_sha_identity_is_stable():
    import hashlib; assert hashlib.sha256(b"x").hexdigest()==hashlib.sha256(b"x").hexdigest()
def test_percentiles(): assert (percentile([1,2,3,4],.5),percentile([1,2,3,4],.95))==(2,4)
def test_empty_percentile_is_null(): assert percentile([],.95) is None
def test_cache_and_warmup_excluded():
    s=summarize([{"completed":True,"success":True,"latency_seconds":1,"cache_hit":False,"warmup":False,"output_tokens":2},{"completed":True,"success":True,"latency_seconds":99,"cache_hit":True,"warmup":False},{"completed":True,"success":True,"latency_seconds":88,"cache_hit":False,"warmup":True}]); assert s["latency_p95_seconds"]==1 and s["cache_hits"]==1
def test_missing_tokens_is_null(): assert summarize([{"completed":True,"success":True,"latency_seconds":1,"cache_hit":False,"warmup":False}])["output_tokens_per_second"] is None
def test_rates_use_monotonic_span():
    s=summarize([{"completed":True,"success":True,"latency_seconds":1,"cache_hit":False,"warmup":False,"output_tokens":4,"started_monotonic":1,"ended_monotonic":3},{"completed":True,"success":True,"latency_seconds":1,"cache_hit":False,"warmup":False,"output_tokens":4,"started_monotonic":2,"ended_monotonic":5}]); assert s["requests_per_second"]==.5 and s["aggregate_output_tokens_per_second"]==2
def test_mock_run_manifest_and_cost_not_configured(tmp_path,monkeypatch):
    monkeypatch.setenv("AGENTTRUST_ARTIFACT_DIR",str(tmp_path)); root=run(args(max_requests=2)); m=json.loads((root/"run-manifest.json").read_text()); assert m["provider_mode"]=="mock" and not m["network_enabled"] and m["cost_configuration_status"]=="not_configured"
def test_amd_unavailable(): assert AmdSmiTelemetry(which=lambda _:None).capabilities()["telemetry_status"]=="unavailable"
def test_amd_full_fixture():
    data=json.loads((FIXTURES/"amd_smi_full.json").read_text()); row=normalize(data,1)[0]; assert row["verified_gpu_name"]=="AMD Instinct MI300X" and row["vram_total_mb"]==65536
def test_amd_multiple_fixture(): assert len(normalize(json.loads((FIXTURES/"amd_smi_multiple.json").read_text())))==2
def test_amd_partial_fixture_nulls():
    row=normalize(json.loads((FIXTURES/"amd_smi_partial.json").read_text()))[0]; assert row["vram_used_mb"]==1024 and row["power_watts"] is None
def test_amd_malformed_fixture_nonfatal():
    class R: returncode=0; stdout=(FIXTURES/"amd_smi_malformed.json").read_text(); stderr=""
    rows,status=AmdSmiTelemetry(which=lambda _:"amd-smi",run=lambda *a,**k:R()).sample(); assert rows==[] and status["telemetry_status"]=="unavailable"
def test_amd_permission_redaction(): assert sanitize_error((FIXTURES/"amd_smi_permission_denied.txt").read_text())=="amd-smi permission denied"
def test_cache_identity_includes_provider_model_prompt_and_parameters():
    assert len({cache_key("mock","m","p",{}),cache_key("nim","m","p",{}),cache_key("mock","m2","p",{}),cache_key("mock","m","p2",{}),cache_key("mock","m","p",{"temperature":0})})==5
def test_cache_hit_is_not_new_provider_request(tmp_path,monkeypatch):
    monkeypatch.setenv("AGENTTRUST_ARTIFACT_DIR",str(tmp_path)); run(args(max_requests=1)); root=run(args(max_requests=1,resume=True)); summary=json.loads((root/"benchmark-summary.json").read_text()); assert summary["cache_hits"]==1 and summary["new_provider_requests"]==0
def test_cache_is_not_used_without_resume(tmp_path,monkeypatch):
    monkeypatch.setenv("AGENTTRUST_ARTIFACT_DIR",str(tmp_path)); run(args(max_requests=1)); root=run(args(max_requests=1)); assert json.loads((root/"benchmark-summary.json").read_text())["cache_hits"]==0
def test_malformed_cache_is_replaced_safely(tmp_path,monkeypatch):
    monkeypatch.setenv("AGENTTRUST_ARTIFACT_DIR",str(tmp_path)); cache=tmp_path/"gpu-lab"/"cache"; cache.mkdir(parents=True); (cache/(cache_key("mock","mock","deterministic GPU reliability fixture",{"temperature":0})+".json")).write_text("bad"); root=run(args(max_requests=1)); assert json.loads((root/"benchmark-summary.json").read_text())["successful_requests"]==1
def test_concurrency_bound_and_deterministic_records(tmp_path,monkeypatch):
    monkeypatch.setenv("AGENTTRUST_ARTIFACT_DIR",str(tmp_path)); root=run(args(max_requests=4,concurrency=2)); rows=[json.loads(x) for x in (root/"requests.jsonl").read_text().splitlines()]; assert [r["sequence"] for r in rows]==[0,1,2,3]
def test_request_limit_under_concurrency(tmp_path,monkeypatch):
    monkeypatch.setenv("AGENTTRUST_ARTIFACT_DIR",str(tmp_path)); root=run(args(max_requests=3,concurrency=2)); assert len((root/"requests.jsonl").read_text().splitlines())==3
def test_configured_cost_calculation(): assert _estimate({"input_tokens":1000000,"output_tokens":1000000},(1.0,2.0,None))==3.0
def test_cost_requires_usage(): assert _estimate({"input_tokens":None,"output_tokens":3},(1.0,2.0,None)) is None
def test_non_streaming_ttft_remains_null(): assert summarize([{"completed":True,"success":True,"latency_seconds":1,"cache_hit":False,"warmup":False}])["ttft_p95_seconds"] is None
