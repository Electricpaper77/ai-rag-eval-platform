from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List
import os
import json
import glob
from pathlib import Path
import time

from .guardrails import redact_pii, check_injection
from .rag import COLLECTION_NAME, get_client, get_collection, query_rag
from .graphrag_retriever import build_graph_index_from_collection, hybrid_retrieve
from .metrics import GRAPHRAG_LATENCY_SECONDS, GRAPHRAG_REQUESTS_TOTAL
from .routes.regression_eval import router as regression_router
from .routes.eval_compare import router as eval_compare_router
from .routes.dashboard import router as dashboard_router
from .routes.agenttrust_demo import router as agenttrust_demo_router
from .routes.nvidia_evaluation import router as nvidia_evaluation_router
from .routes.recruiter_golden_path import router as recruiter_golden_path_router
from .routes.gpu_lab import router as gpu_lab_router
from .inference import handle_chat_completions
from gpu_platform.api import router as platform_router
from gpu_platform.api import summary_router as shadow_eval_router
from gpu_platform.api import benchmark_router
from .control_plane import router as gpu_control_plane_router

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

app = FastAPI(title="AI RAG Eval Platform")
app.include_router(regression_router)
app.include_router(eval_compare_router)
app.include_router(dashboard_router)
app.include_router(agenttrust_demo_router)
app.include_router(nvidia_evaluation_router)
app.include_router(recruiter_golden_path_router)
app.include_router(gpu_lab_router)
app.include_router(platform_router)
app.include_router(shadow_eval_router)
app.include_router(benchmark_router)
app.include_router(gpu_control_plane_router)


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
from starlette.responses import Response


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/chat/completions")
async def chat_completions_openai_compatible(request: dict):
    try:
        return await handle_chat_completions(request)
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
def evaluate(request: EvaluateRequest):
    return query_guarded(QueryRequest(question=request.prompt, top_k=request.top_k))


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
