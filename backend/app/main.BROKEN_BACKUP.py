from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, List
import os
import glob
import time

app = FastAPI(title="AI RAG Eval Platform")

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

    # clamp top_k to avoid weird values
    top_k = int(req.top_k or 4)
    top_k = max(1, min(top_k, 10))

    try:
        results = collection.query(query_texts=[q], n_results=top_k)
    except Exception:
        return {"status": "error", "message": "No index found. Run /ingest first.", "answer": "", "citations": []}

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log_run(q, top_k, "No matches found.", [], latency_ms)
        return {"status": "ok", "question": q, "answer": "No matches found.", "citations": [], "latency_ms": latency_ms}

    citations: List[Dict[str, Any]] = []
    for meta, dist in zip(metas, dists):
        src = (meta or {}).get("source", "")
        chunk = (meta or {}).get("chunk", -1)
        citations.append({"source": src, "chunk": chunk, "distance": dist})

    # Build a clean 1-sentence answer from the top retrieved chunk
    top_doc = docs[0] or ""
    snippet = top_doc.replace("\n", " ").strip()

    # naive sentence split; keeps it robust without extra deps
    parts = [p.strip() for p in snippet.split(".") if p.strip()]

    if not parts:
        final_answer = "No matches found."
    elif len(parts) == 1:
        final_answer = parts[0] + "."
    else:
        # make it ONE sentence by joining with semicolons
        final_answer = "; ".join(parts[:2]) + "."

    latency_ms = int((time.perf_counter() - t0) * 1000)
    log_run(q, top_k, final_answer, citations, latency_ms)

    return {
        "status": "ok",
        "question": q,
        "answer": final_answer,
        "citations": citations,
        "latency_ms": latency_ms,
    }


@app.post("/eval/run")
def eval_run() -> Dict[str, Any]:

    results_out = []
    passed = 0

    for case in cases:
        q = case["question"]

        qr = QueryRequest(question=q, top_k=4)
        result = query(qr)

        score = score_case(case, result)

        if score["overall_pass"]:
            passed += 1

        results_out.append({
            "id": case.get("id"),
            "question": q,
            "answer": result.get("answer"),
            "top_source": result.get("top_source"),
            "latency_ms": result.get("latency_ms"),
            "score": score,
        })

    total = len(cases)
    pass_rate = round((passed / total * 100.0), 1) if total else 0.0

    return {
        "status": "ok",
        "summary": {
            "total_cases": total,
            "passed": passed,
            "pass_rate_pct": pass_rate,
        },
        "results": results_out,
    }








