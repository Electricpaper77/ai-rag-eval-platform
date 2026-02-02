from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import os
from .guardrails import redact_pii, check_injection
import glob
from .guardrails import redact_pii, check_injection
import time
from pathlib import Path
from .guardrails import redact_pii, check_injection

import chromadb
from .guardrails import redact_pii, check_injection
from chromadb.config import Settings

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
# FIXED: was invalid docstring ->     \"\"\"Resolve ingest folder robustly in Cloud Run/buildpacks.\"\"\"
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

CHROMA_DIR = os.getenv("CHROMA_DIR", "/tmp/chroma")
EVAL_DIR = os.path.join(PROJECT_ROOT, "data", "eval_sets")
DEFAULT_EVAL_SET = os.path.join(EVAL_DIR, "policy_eval.json")
COLLECTION_NAME = "docs"

app = FastAPI(title="AI RAG Eval Platform")


# ----------------------------
# Request models
# ----------------------------
class IngestRequest(BaseModel):
    path: str = DATA_DIR_DEFAULT


class QueryRequest(BaseModel):
    question: str
    top_k: int = 4


# ----------------------------
# Helpers
# ----------------------------
def get_client() -> chromadb.PersistentClient:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(allow_reset=True),
    )


def get_collection(client: chromadb.PersistentClient):
    # Create/get collection
    return client.get_or_create_collection(name=COLLECTION_NAME)


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
        try:
            with open(DEFAULT_EVAL_SET, "r", encoding="utf-8-sig") as f:
                eval_blob = json.load(f)
            if text.strip():
                docs.append({"path": path.replace("\\", "/"), "text": text})
        except Exception:
            continue
    return docs


def chunk_text(text: str, max_chars: int = 1200) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    chunks: List[str] = []
    i = 0
    while i < len(t):
        chunk = t[i : i + max_chars].strip()
        if chunk:
            chunks.append(chunk)
        i += max_chars
    return chunks


def make_answer_from_snippets(question: str, snippets: List[str]) -> str:
    # Minimal “demo” answer: 1–2 best snippets joined.
    if not snippets:
        return "I couldn’t find an answer in the documents."
    best = snippets[0].strip()
    if len(snippets) > 1:
        second = snippets[1].strip()
        return f"{best}\n\n{second}"
    return best


# ----------------------------
# Routes
# ----------------------------
@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/stats")
def stats() -> Dict[str, Any]:
    client = get_client()
    collection = get_collection(client)
    try:
        count = collection.count()
    except Exception:
        count = 0
    return {"status": "ok", "collection": COLLECTION_NAME, "count": count}


@app.post("/ingest")
def ingest(req: IngestRequest) -> Dict[str, Any]:
    folder = req.path
    if not os.path.isdir(folder):
        return {"status": "error", "message": f"Folder not found: {folder}"}

    # Load docs from local folder OR GCS

    docs: List[Dict[str, str]] = []

    if req.path.startswith("gs://"):

        folder = req.path

        try:

            for fname, text in iter_gcs_text_files(req.path):

                docs.append({"path": fname, "text": text})

        except Exception as e:

            return {"status": "error", "message": f"GCS ingest failed: {e}"}




    if not docs:

        return {"status": "error", "message": f"No .md or .txt files found in: {folder}"}

    client = get_client()

    # reset collection for deterministic demo runs
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = get_collection(client)

    ids: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    documents: List[str] = []

    doc_count = 0
    chunk_count = 0

    for d in docs:
        doc_count += 1
        chunks = chunk_text(d["text"])
        for i, c in enumerate(chunks):
            chunk_id = f"{os.path.basename(d['path'])}::chunk_{i}"
            ids.append(chunk_id)
            documents.append(c)
            metadatas.append({"source": d["path"], "chunk": i})
            chunk_count += 1

    collection.add(ids=ids, documents=documents, metadatas=metadatas)

    return {
        "status": "ok",
        "ingested_folder": folder.replace("\\", "/"),
        "documents": doc_count,
        "chunks": chunk_count,
        "collection": COLLECTION_NAME,
    }


@app.post("/query")
def query(req: QueryRequest) -> Dict[str, Any]:
    t0 = time.perf_counter()

    q = (req.question or "").strip()
    if not q:
        return {"status": "error", "message": "Question is empty.", "answer": "", "citations": []}

    client = get_client()
    collection = get_collection(client)

    res = collection.query(query_texts=[q], n_results=int(req.top_k))
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]

    citations: List[Dict[str, Any]] = []
    for i in range(min(len(docs), len(metas))):
        citations.append(
            {
                "rank": i + 1,
                "source": metas[i].get("source"),
                "chunk": metas[i].get("chunk"),
                "snippet": docs[i][:240],
            }
        )

    answer = make_answer_from_snippets(q, docs)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "status": "ok",
        "question": q,
        "answer": answer,
        "citations": citations,
        "num_citations": len(citations),
        "latency_ms": latency_ms,
        "top_source": citations[0]["source"] if citations else None,
    }



@app.post("/query_guarded")
def query_guarded(req: QueryRequest) -> Dict[str, Any]:
    # Block obvious prompt-injection attempts
    hit, reason = check_injection(req.question)
    if hit:
        return {"status": "blocked", "reason": reason}

    # Redact PII before retrieval
    safe_q = redact_pii(req.question)

    # Reuse the same retrieval stack as /query
    client = get_client()
    collection = get_collection(client)
    results = collection.query(query_texts=[safe_q], n_results=req.top_k)

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    citations = []
    for i, (d, m) in enumerate(zip(docs, metas), start=1):
        citations.append({
            "rank": i,
            "source": m.get("source"),
            "chunk": m.get("chunk"),
            "snippet": d[:300],
        })

    answer = "\n".join([c["snippet"] for c in citations]) if citations else "No results."
    return {
        "status": "ok",
        "question": safe_q,
        "answer": answer,
        "citations": citations,
        "num_citations": len(citations),
        "top_source": citations[0]["source"] if citations else None,
    }

@app.post("/eval/run")
def eval_run() -> Dict[str, Any]:
    """
    Minimal eval: runs 3 questions and reports citation hit-rate + avg latency.
    If backend/data/eval_sets/policy_eval.json exists, uses that file.
    """
    # load eval set if present
    eval_cases: List[Dict[str, Any]] = []
    if os.path.isfile(DEFAULT_EVAL_SET):
        import json
        with open(DEFAULT_EVAL_SET, "r", encoding="utf-8-sig") as f:
            eval_blob = json.load(f)
            eval_cases = eval_blob.get("cases", eval_blob) if isinstance(eval_blob, dict) else eval_blob
            
    # fallback eval
    if not eval_cases:
        eval_cases = [
            {"id": "refund_1", "question": "What is the refund policy?"},
            {"id": "ship_1", "question": "How long does shipping take?"},
            {"id": "support_1", "question": "What are the support hours?"},
        ]

    results_out: List[Dict[str, Any]] = []
    questions_with_citations = 0
    total_latency = 0

    for case in eval_cases:
        q = case["question"]
        r = query(QueryRequest(question=q, top_k=4))
        total_latency += int(r.get("latency_ms") or 0)

        num_citations = int(r.get("num_citations") or 0)
        if num_citations > 0:
            questions_with_citations += 1

        results_out.append(
            {
                "id": case.get("id"),
                "question": q,
                "latency_ms": r.get("latency_ms"),
                "num_citations": num_citations,
                "top_source": r.get("top_source"),
                "answer": r.get("answer"),
            }
        )

    total_questions = len(eval_cases)
    hit_rate_pct = (questions_with_citations / total_questions * 100.0) if total_questions else 0.0
    avg_latency_ms = (total_latency / total_questions) if total_questions else 0.0

    return {
        "status": "ok",
        "results": results_out,
        "stats": {
            "total_questions": total_questions,
            "questions_with_citations": questions_with_citations,
            "hit_rate_pct": round(hit_rate_pct, 1),
            "avg_latency_ms": round(avg_latency_ms, 1),
        },
    }




















