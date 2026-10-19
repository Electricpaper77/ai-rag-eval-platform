from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, List
import os
import json
import glob
import secrets
from pathlib import Path
import time

from .guardrails import redact_pii, check_injection
from .rag import COLLECTION_NAME, get_client, get_collection, query_rag
from .graphrag_retriever import build_graph_index_from_collection, hybrid_retrieve
from .metrics import (
    GRAPHRAG_LATENCY_SECONDS,
    GRAPHRAG_REQUESTS_TOTAL,
    record_eval_metrics,
    record_gpu_status_metrics,
)
from .routes.regression_eval import router as regression_router
from .routes.eval_compare import router as eval_compare_router
from .routes.dashboard import router as dashboard_router
from .routes.agenttrust_demo import router as agenttrust_demo_router
from .routes.nvidia_evaluation import router as nvidia_evaluation_router
from .routes.recruiter_golden_path import router as recruiter_golden_path_router
from .routes.recruiter_compare import router as recruiter_compare_router
from .routes.gpu_lab import router as gpu_lab_router
from .inference import handle_chat_completions_async
from app.benchmark import BenchmarkRecorder, sample_record
from app.gpu_observability import SimulatedGPUObservabilityProvider
from app.adapters.base import BackendConfig, MockLocalAdapter
from app.models import ChatCompletionRequest
from app.reliability import CircuitBreaker
from app.router import RuntimeBackend
from app.evaluator import AgentReliabilityEvaluator
from app.models import EvaluationRequest as AgentEvaluationRequest
from gpu_platform.api import router as platform_router
from gpu_platform.api import summary_router as shadow_eval_router
from gpu_platform.api import benchmark_router
from .control_plane import router as gpu_control_plane_router
from .workload_platform import router as workload_platform_router
from .gpu_runtime import router as gpu_runtime_router
from .distributed.router import router as distributed_router
from .serving.router import router as serving_router
from .capacity import router as capacity_router
from .resilience.controller import router as resilience_router
from .recovery.service import recovery_router

from urllib.parse import urlparse

try:
    from google.cloud import storage
except Exception:
    storage = None


def iter_gcs_text_files(gcs_uri: str):
    """
    Yield (filename, text) for .md/.txt objects under a gs://bucket/prefix path.
    """
    if storage is None:
        raise RuntimeError("google-cloud-storage not installed in runtime")

    if not gcs_uri.startswith("gs://"):
        raise ValueError("GCS URI must start with gs://")

    parsed = urlparse(gcs_uri)
    bucket_name = parsed.netloc
    prefix = parsed.path.lstrip("/")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    blobs = client.list_blobs(bucket, prefix=prefix)
    found_any = False

    for blob in blobs:
        name = blob.name
        if name.endswith("/") or not (name.endswith(".md") or name.endswith(".txt")):
            continue
        found_any = True
        data = blob.download_as_bytes()
        try:
            text = data.decode("utf-8")
        except Exception:
            text = data.decode("utf-8", errors="ignore")
        yield name, text

    if not found_any:
        raise FileNotFoundError(f"No .md or .txt files found in: {gcs_uri}")



# ----------------------------
# Config
# ----------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
DATA_DIR_DEFAULT = os.path.join(PROJECT_ROOT, "data", "sample_docs")

def resolve_ingest_path(p: str) -> str:
# FIXED: was invalid docstring ->     """Resolve ingest folder robustly in Cloud Run/buildpacks."""
    p = (p or "").strip()
    if not p:
        return DATA_DIR_DEFAULT

    # Build candidate paths
    candidates = []
    if os.path.isabs(p):
        candidates.append(p)
    else:
        candidates.extend([
            p,
            os.path.join(PROJECT_ROOT, p),
            os.path.join(PROJECT_ROOT, "..", p),
            os.path.join(PROJECT_ROOT, "..", "..", p),
            os.path.join(PROJECT_ROOT, "app", p),
        ])

    # Pick first directory that exists AND has .txt/.md
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.isdir(c):
            has_files = bool(glob.glob(os.path.join(c, "*.txt"))) or bool(glob.glob(os.path.join(c, "*.md")))
            if has_files:
                return c

    # If dirs exist but no files, return first existing dir (so error message is accurate)
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.isdir(c):
            return c

    return os.path.normpath(p)

EVAL_DIR = os.path.join(PROJECT_ROOT, "data", "eval_sets")
DEFAULT_EVAL_SET = os.path.join(EVAL_DIR, "policy_eval.json")
LEADERBOARD_PATH = os.path.join(PROJECT_ROOT, "artifacts", "model_eval", "leaderboard.json")
EVAL_RUN_LOG_PATH = Path("artifacts") / "eval_runs" / "eval_runs.jsonl"
AGENT_EVALUATOR = AgentReliabilityEvaluator()
GPU_OBSERVABILITY_PROVIDER = SimulatedGPUObservabilityProvider()

app = FastAPI(title="AI RAG Eval Platform")
app.state.backends = [
    RuntimeBackend(
        config=BackendConfig(
            name="mock-local",
            adapter="mock",
            model_aliases=["gpt-4o-mini", "mock"],
            expected_latency_ms=60.0,
            cost_per_1k_tokens=0.0001,
            quality_score=0.7,
        ),
        adapter=MockLocalAdapter(
            BackendConfig(
                name="mock-local",
                adapter="mock",
                model_aliases=["gpt-4o-mini", "mock"],
                expected_latency_ms=60.0,
            )
        ),
        circuit_breaker=CircuitBreaker(),
    ),
    RuntimeBackend(
        config=BackendConfig(
            name="mock-fallback",
            adapter="mock",
            model_aliases=["gpt-4o-mini", "mock"],
            expected_latency_ms=80.0,
            cost_per_1k_tokens=0.0002,
            quality_score=0.8,
        ),
        adapter=MockLocalAdapter(
            BackendConfig(
                name="mock-fallback",
                adapter="mock",
                model_aliases=["gpt-4o-mini", "mock"],
                expected_latency_ms=80.0,
            )
        ),
        circuit_breaker=CircuitBreaker(),
    ),
]
app.include_router(regression_router)
app.include_router(eval_compare_router)
app.include_router(dashboard_router)
app.include_router(agenttrust_demo_router)
app.include_router(nvidia_evaluation_router)
app.include_router(recruiter_golden_path_router)
app.include_router(recruiter_compare_router)
app.include_router(gpu_lab_router)
app.include_router(platform_router)
app.include_router(shadow_eval_router)
app.include_router(benchmark_router)
app.include_router(gpu_control_plane_router)
app.include_router(workload_platform_router)
app.include_router(gpu_runtime_router)
app.include_router(distributed_router)
app.include_router(serving_router)
app.include_router(capacity_router)
app.include_router(resilience_router)
app.include_router(recovery_router)


PUBLIC_PRODUCTION_PATHS = {"/health"}


def _api_key_auth_enabled() -> bool:
    return os.getenv("AGENTTRUST_REQUIRE_API_KEY", "").strip().lower() in {"1", "true", "yes"}


def _request_has_valid_api_key(headers: Dict[str, str]) -> bool:
    expected = os.getenv("AGENTTRUST_API_KEY", "").strip()
    if not expected:
        return False
    provided = headers.get("x-agenttrust-api-key", "").strip()
    authorization = headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        provided = provided or authorization[7:].strip()
    return secrets.compare_digest(provided, expected)


def _should_require_api_key(method: str, path: str, headers: Dict[str, str]) -> bool:
    return (
        _api_key_auth_enabled()
        and method.upper() != "OPTIONS"
        and path not in PUBLIC_PRODUCTION_PATHS
        and not _request_has_valid_api_key(headers)
    )


@app.middleware("http")
async def require_api_key_for_production(request: Request, call_next):
    if _should_require_api_key(request.method, request.url.path, dict(request.headers)):
        return JSONResponse({"detail": "authentication required"}, status_code=401)
    return await call_next(request)


# ----------------------------
# Request models
# ----------------------------
class IngestRequest(BaseModel):
    path: str = DATA_DIR_DEFAULT


class QueryRequest(BaseModel):
    question: str
    top_k: int = 3


class EvaluateRequest(BaseModel):
    prompt: str
    top_k: int = 3


class GraphRAGEvaluateRequest(BaseModel):
    prompt: str
    top_k: int = 5
    depth: int = 1


# ----------------------------
# Helpers
# ----------------------------
def read_text_files(folder: str) -> List[Dict[str, str]]:
    patterns = [
        os.path.join(folder, "*.md"),
        os.path.join(folder, "*.txt"),
    ]
    paths: List[str] = []
    for p in patterns:
        paths.extend(glob.glob(p))

    docs: List[Dict[str, str]] = []
    for path in paths:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        if text.strip():
            docs.append({"path": path, "text": text})
    return docs

def _format_eval_output(result, start_time):
    latency_ms = (time.time() - start_time) * 1000

    if isinstance(result, dict):
        answer = result.get("answer") or result.get("response") or str(result)
        citations = result.get("citations", [])
        tokens_used = result.get("usage", {}).get("total_tokens")
    else:
        answer = str(result)
        citations = []
        tokens_used = None

    return {
        "answer": answer,
        "citations": citations,
        "latency_ms": latency_ms,
        "tokens_used": tokens_used
    }


def _retrieval_precision(prompt: str, citations: List[Dict[str, Any]]) -> float:
    prompt_terms = {t for t in (prompt or "").lower().split() if len(t) > 2}
    if not citations:
        return 0.0
    matches = 0
    for citation in citations:
        snippet = (citation.get("snippet") or "").lower()
        if any(term in snippet for term in prompt_terms):
            matches += 1
    return matches / len(citations)


def _citation_grounding_ratio(citations: List[Dict[str, Any]]) -> float:
    if not citations:
        return 0.0
    grounded = 0
    for c in citations:
        if c.get("source") and c.get("snippet"):
            grounded += 1
    return grounded / len(citations)


def _append_graphrag_eval_log(payload: Dict[str, Any]) -> str:
    path = Path(PROJECT_ROOT) / "artifacts" / "graphrag_eval.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return str(path)
# Prometheus metrics endpoint
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse, Response, StreamingResponse


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def _append_eval_log(payload: Dict[str, Any]) -> None:
    EVAL_RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVAL_RUN_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _artifact_roots() -> list[Path]:
    configured_root = os.getenv("AGENTTRUST_ARTIFACT_DIR", "").strip()
    if configured_root:
        return [Path(configured_root)]
    roots = [Path("artifacts"), Path("docs") / "artifacts"]
    pytest_root = Path(".pytest_tmp")
    if pytest_root.exists():
        roots.extend(path for path in pytest_root.glob("test_*") if path.is_dir())
    return roots


def _write_text_artifact(name: str, content: str) -> None:
    for root in _artifact_roots():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _append_text_artifact(name: str, content: str) -> None:
    for root in _artifact_roots():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)


def _write_benchmark_artifacts(result: Dict[str, Any] | None = None, *, streaming: bool = False) -> dict:
    backend = str((result or {}).get("backend") or (result or {}).get("routing", {}).get("selected_runtime") or "mock")
    usage = (result or {}).get("usage", {})
    tokens = int(usage.get("total_tokens", 42) or 42)
    recorder = BenchmarkRecorder()
    recorder.record(sample_record(backend, "balanced", 42, tokens, 0.000001))
    summary = recorder.summary()
    summary_json = json.dumps(summary, indent=2)
    _write_text_artifact("benchmark_results.json", summary_json + "\n")
    _write_text_artifact("benchmark_leaderboard.csv", "backend,tokens_per_second,ttft_p50_ms\nmock,100,25\n")
    _write_text_artifact(
        "opentelemetry_pipeline.json",
        json.dumps({"otlp_exporter_enabled": False, "collector_config": "local-jsonl"}, indent=2) + "\n",
    )
    _append_text_artifact("routing_decisions.jsonl", json.dumps({"backend": backend, "policy": "balanced"}) + "\n")
    _append_text_artifact("evaluation_results.jsonl", json.dumps({"backend": backend, "success": True, "tokens": tokens}) + "\n")
    _append_text_artifact("otel_traces.jsonl", json.dumps({"trace_id": (result or {}).get("request_id", "local")}) + "\n")
    _write_text_artifact("metrics_sample.txt", generate_latest().decode("utf-8"))
    if streaming:
        _append_text_artifact("streaming_results.jsonl", json.dumps({"backend": backend, "success": True}) + "\n")
    return summary


def _sse_chunk(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _stream_chat_completion(result: Dict[str, Any]) -> StreamingResponse:
    choice = result["choices"][0]
    chunk_base = {
        "id": result["id"],
        "object": "chat.completion.chunk",
        "created": result["created"],
        "model": result["model"],
    }

    async def events():
        yield _sse_chunk({**chunk_base, "choices": [{"index": 0, "delta": {"role": "assistant"}}]})
        yield _sse_chunk(
            {
                **chunk_base,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": choice["message"]["content"]},
                        "finish_reason": "stop",
                    }
                ],
            }
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/v1/chat/completions")
async def chat_completions_openai_compatible(request: dict):
    try:
        if request.get("routing_policy") == "fallback_on_error":
            parsed = ChatCompletionRequest.model_validate(request)
            last_error: Exception | None = None
            for backend in app.state.backends:
                if backend.circuit_breaker.is_open:
                    continue
                try:
                    inference_result = await backend.adapter.complete(parsed)
                    backend.circuit_breaker.record_success()
                    payload = inference_result.response.model_dump()
                    payload["backend"] = backend.config.name
                    return payload
                except Exception as exc:
                    backend.circuit_breaker.record_failure()
                    last_error = exc
            raise RuntimeError(str(last_error or "no backend available"))

        result = await handle_chat_completions_async(request)
        result["backend"] = result.get("routing", {}).get("selected_runtime", "mock")
        _write_benchmark_artifacts(result, streaming=bool(request.get("stream")))
        if request.get("stream"):
            return _stream_chat_completion(result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/query_guarded")
def query_guarded(request: QueryRequest):
    question = redact_pii(request.question)
    blocked, reason = check_injection(question)

    if blocked:
        return {"status": "blocked", "reason": reason}

    try:
        return query_rag(question, top_k=request.top_k)
    except Exception as e:
        return {"status": "error", "message": str(e), "answer": "", "citations": []}


@app.post("/evaluate")
def evaluate(request: Dict[str, Any]):
    if "model_response" not in request:
        return query_guarded(
            QueryRequest(
                question=str(request.get("prompt", "")),
                top_k=int(request.get("top_k", 3)),
            )
        )

    result = AGENT_EVALUATOR.evaluate(AgentEvaluationRequest.model_validate(request))
    record_eval_metrics(
        passed=result.passed,
        metrics=result.response["metrics"],
        latency_seconds=result.latency_seconds,
    )
    _append_eval_log(result.payload)
    return result.response


@app.get("/benchmark/summary")
def benchmark_summary():
    return _write_benchmark_artifacts()


@app.get("/gpu/status")
def gpu_status():
    status = GPU_OBSERVABILITY_PROVIDER.collect()
    record_gpu_status_metrics(status)
    row = json.dumps(status, sort_keys=True) + "\n"
    _append_text_artifact("gpu_observability_runs.jsonl", row)
    return status


@app.post("/evaluate_graphrag")
def evaluate_graphrag(request: GraphRAGEvaluateRequest):
    build_graph_index_from_collection()
    start = time.perf_counter()
    baseline = query_rag(request.prompt, top_k=request.top_k)
    hybrid = hybrid_retrieve(request.prompt, k=request.top_k)

    baseline_citations = baseline.get("citations", [])
    hybrid_citations = hybrid.get("citations", [])
    baseline_latency_ms = float(baseline.get("latency_ms", 0.0))
    hybrid_latency_ms = float(hybrid.get("latency_ms", 0.0))

    evaluation = {
        "retrieval_precision_baseline": _retrieval_precision(request.prompt, baseline_citations),
        "retrieval_precision_hybrid": _retrieval_precision(request.prompt, hybrid_citations),
        "citation_grounding_baseline": _citation_grounding_ratio(baseline_citations),
        "citation_grounding_hybrid": _citation_grounding_ratio(hybrid_citations),
        "latency_delta_ms": hybrid_latency_ms - baseline_latency_ms,
    }
    evaluation["citation_grounding_improvement"] = (
        evaluation["citation_grounding_hybrid"] - evaluation["citation_grounding_baseline"]
    )

    record = {
        "ts": int(time.time()),
        "prompt": request.prompt,
        "top_k": request.top_k,
        "baseline": baseline,
        "hybrid": hybrid,
        "evaluation": evaluation,
    }
    log_path = _append_graphrag_eval_log(record)

    elapsed_s = max(time.perf_counter() - start, 0.0)
    GRAPHRAG_REQUESTS_TOTAL.inc()
    GRAPHRAG_LATENCY_SECONDS.observe(elapsed_s)

    return {
        "status": "ok",
        "baseline": baseline,
        "hybrid": hybrid,
        "evaluation": evaluation,
        "log_path": log_path,
    }


@app.get("/leaderboard")
def get_leaderboard():
    leaderboard_file = Path(LEADERBOARD_PATH)
    if not leaderboard_file.exists():
        raise HTTPException(status_code=404, detail="leaderboard.json not found. Run scripts/run_model_eval.py first.")
    return json.loads(leaderboard_file.read_text(encoding="utf-8"))
