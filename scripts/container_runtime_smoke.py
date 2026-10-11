from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SECRET_CANARY = "agenttrust-secret-canary-do-not-leak"


def _request(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | str]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            text = response.read().decode("utf-8")
            return response.status, _parse_body(text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        return exc.code, _parse_body(text)


def _parse_body(text: str) -> dict[str, Any] | str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    return parsed


def _wait_for_health(base_url: str, attempts: int, delay_seconds: float) -> dict[str, Any]:
    last_error: str | None = None
    for _ in range(attempts):
        try:
            status, body = _request("GET", f"{base_url}/health")
            if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                return {"status_code": status, "body": body}
            last_error = f"unexpected health response: {status} {body}"
        except Exception as exc:  # noqa: BLE001 - surfaced in evidence for readiness diagnosis.
            last_error = repr(exc)
        time.sleep(delay_seconds)
    raise RuntimeError(f"container did not become ready: {last_error}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _assert_no_secret_leak(payload: Any) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    if SECRET_CANARY in serialized:
        raise AssertionError("secret canary leaked into runtime evidence")


def run_smoke(base_url: str, artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    health = _wait_for_health(base_url, attempts=30, delay_seconds=2.0)

    endpoint_results: dict[str, Any] = {"health": health}
    for path in ("/metrics", "/openapi.json"):
        status, body = _request("GET", f"{base_url}{path}")
        if status != 200:
            raise AssertionError(f"{path} returned {status}: {body}")
        endpoint_results[path] = {
            "status_code": status,
            "content_check": "AI RAG Eval Platform" if path == "/openapi.json" else "prometheus_text",
        }
        if path == "/openapi.json":
            assert isinstance(body, dict)
            assert body["info"]["title"] == "AI RAG Eval Platform"

    valid_eval_payload = {
        "prompt": "Summarize the deployment status from the provided report.",
        "model_response": "The deployment passed health checks and stayed within latency SLOs. [1]",
        "expected_behavior": "Answer accurately and include a citation.",
        "risk_category": "citation",
        "retrieved_evidence": [
            {
                "source_id": "1",
                "snippet": "The deployment passed health checks and stayed within latency SLOs.",
            }
        ],
        "metadata": {"suite": "gate12-container-runtime-smoke"},
    }
    eval_status, eval_body = _request("POST", f"{base_url}/evaluate", valid_eval_payload)
    if eval_status != 200 or not isinstance(eval_body, dict):
        raise AssertionError(f"valid evaluation failed: {eval_status} {eval_body}")
    assert eval_body["pass"] is True
    eval_run_id = str(eval_body["run_id"])

    invalid_status, invalid_body = _request("POST", f"{base_url}/v1/chat/completions", {"model": "gpt-4o-mini"})
    if invalid_status != 400 or not isinstance(invalid_body, dict):
        raise AssertionError(f"invalid chat request did not return safe 400: {invalid_status} {invalid_body}")
    assert "messages field required" in str(invalid_body.get("detail", ""))

    fallback_payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Return one sentence about container runtime validation."}],
        "max_tokens": 32,
        "gpu_availability": False,
    }
    chat_status, chat_body = _request("POST", f"{base_url}/v1/chat/completions", fallback_payload)
    if chat_status != 200 or not isinstance(chat_body, dict):
        raise AssertionError(f"mock fallback chat request failed: {chat_status} {chat_body}")
    routing = chat_body.get("routing") or {}
    assert routing.get("selected_runtime") == "mock"
    assert routing.get("gpu_availability") is False
    request_id = str(chat_body.get("request_id") or chat_body.get("id"))

    eval_logs = _read_jsonl(artifact_dir / "eval_runs" / "eval_runs.jsonl")
    inference_logs = _read_jsonl(artifact_dir / "inference_runs.jsonl")
    matching_eval = [row for row in eval_logs if row.get("run_id") == eval_run_id]
    matching_inference = [row for row in inference_logs if row.get("request_id") == request_id]
    if not matching_eval:
        raise AssertionError(f"no eval JSONL log found for run_id={eval_run_id}")
    if not matching_inference:
        raise AssertionError(f"no inference JSONL log found for request_id={request_id}")
    assert str(matching_eval[-1].get("trace_id", "")).startswith("trace-")

    report = {
        "base_url": base_url,
        "endpoints": endpoint_results,
        "valid_evaluation": {
            "status_code": eval_status,
            "run_id": eval_run_id,
            "pass": eval_body["pass"],
            "metric_keys": sorted((eval_body.get("metrics") or {}).keys()),
        },
        "invalid_request": {
            "status_code": invalid_status,
            "detail": invalid_body.get("detail"),
        },
        "mock_fallback_when_gpu_unavailable": {
            "status_code": chat_status,
            "request_id": request_id,
            "selected_runtime": routing.get("selected_runtime"),
            "gpu_availability": routing.get("gpu_availability"),
        },
        "request_id_tracing": {
            "eval_run_id_logged": eval_run_id,
            "eval_trace_id": matching_eval[-1]["trace_id"],
            "chat_request_id_logged": request_id,
        },
        "log_counts": {
            "eval_runs": len(eval_logs),
            "inference_runs": len(inference_logs),
        },
        "latency_scope": "HTTP container runtime smoke only; not synthetic evaluator benchmark latency",
        "gpu_benchmark_caveat": (
            "CI GPU Benchmark server_unavailable/zero-throughput records are schema evidence only, "
            "not actual GPU performance evidence."
        ),
    }
    _assert_no_secret_leak(report)
    _assert_no_secret_leak(eval_logs)
    _assert_no_secret_leak(inference_logs)
    (artifact_dir / "container_runtime_smoke_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AgentTrust Docker container runtime over HTTP.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--artifact-dir", default="artifacts")
    args = parser.parse_args()
    report = run_smoke(args.base_url.rstrip("/"), Path(args.artifact_dir))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
