from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, List
import os
import glob
import time

import chromadb
from chromadb.config import Settings

from .log_run import log_run  # keep relative import


app = FastAPI(title="AI RAG Eval Platform")

DATA_DIR_DEFAULT = "data/sample_docs"
CHROMA_DIR = "data/chroma"
COLLECTION_NAME = "docs"


class IngestRequest(BaseModel):
    path: str = DATA_DIR_DEFAULT


class QueryRequest(BaseModel):
    question: str
    top_k: int = 4


def get_client() -> chromadb.PersistentClient:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(allow_reset=True),
    )


def get_collection(client: chromadb.PersistentClient):
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def read_text_files(folder: str) -> List[Dict[str, str]]:
    patterns = ["*.md", "*.txt"]
    files: List[str] = []
    for p in patterns:
        files.extend(glob.glob(os.path.join(folder, p)))

    out: List[Dict[str, str]] = []
    for fpath in files:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
            out.append({"path": fpath, "text": fh.read()})
    return out


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = max(0, end - overlap)

    return chunks


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest) -> Dict[str, Any]:
    folder = req.path
    if not os.path.isdir(folder):
        return {"status": "error", "message": f"Folder not found: {folder}"}

    docs = read_text_files(folder)
    if not docs:
        return {"status": "error", "message": f"No .md or .txt files found in: {folder}"}

    client = get_client()

    # Reset collection for deterministic demo runs
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
        "ingested_folder": folder,
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

    try:
        results = collection.query(query_texts=[q], n_results=req.top_k)
    except Exception:
        return {"status": "error", "message": "No index found. Run /ingest first.", "answer": "", "citations": []}

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        return {"status": "ok", "question": q, "answer": "No matches found.", "citations": []}

    citations = []
    context_blocks = []
    for doc, meta, dist in zip(docs, metas, dists):
        src = meta.get("source", "")
        chunk = meta.get("chunk", -1)
        citations.append({"source": src, "chunk": chunk, "distance": dist})
        snippet = doc[:300].replace("\n", " ").strip()
        context_blocks.append(f"- {os.path.basename(src)} (chunk {chunk}): {snippet}...")

    answer = "Top matching context:\n" + "\n".join(context_blocks)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    log_run(q, req.top_k, answer, citations, latency_ms)

    return {"status": "ok", "question": q, "answer": answer, "citations": citations}


@app.post("/eval/run")
def eval_run() -> Dict[str, Any]:
    # Minimal eval: run a small fixed set of questions through the existing /query logic
    eval_questions = [
        "What is the refund policy?",
        "How long does shipping take?",
        "What are the support hours?"
    ]

    results = []
    for q in eval_questions:
        # Reuse the same query pipeline by calling the existing query() handler logic indirectly:
        # We'll simply call the same code path by using the same retrieval/generation variables already in this file.
        t0 = time.perf_counter()

        # ---- START: replicate the same logic used in /query ----
        # NOTE: This assumes you already have `collection` available globally (as used by /query)
        
        client = get_client()
        collection = get_collection(client)


        res = collection.query(
            query_texts=[q],
            n_results=4,
            include=["documents", "metadatas", "distances"]
        )
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]

        if not docs:
            answer = "No matches found."
            citations = []
        else:
            citations = []
            context_blocks = []
            for doc, meta, dist in zip(docs, metas, dists):
                src = meta.get("source", "")
                chunk = meta.get("chunk", -1)
                citations.append({"source": src, "chunk": chunk, "distance": dist})
                snippet = doc[:300].replace("\n", " ").strip()
                context_blocks.append(f"- {os.path.basename(src)} (chunk {chunk}): {snippet}...")

            answer = "Top matching context:\n" + "\n".join(context_blocks)

        latency_ms = int((time.perf_counter() - t0) * 1000)

        # This is the key: log one row per question (CSV/JSON logging handled by your existing helper)
        log_run(q, 4, answer, citations, latency_ms)
        # ---- END ----

        results.append({
            "question": q,
            "latency_ms": latency_ms,
            "num_citations": len(citations),
            "top_source": citations[0]["source"] if citations else None
        })

    return {"status": "ok", "results": results}

