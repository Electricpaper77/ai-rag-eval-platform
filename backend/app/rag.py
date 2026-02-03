import os
import time
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings

CHROMA_DIR = os.getenv("CHROMA_DIR", "/tmp/chroma")
COLLECTION_NAME = "docs"


def get_client() -> chromadb.PersistentClient:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(allow_reset=True),
    )


def get_collection(client: chromadb.PersistentClient):
    return client.get_or_create_collection(name=COLLECTION_NAME)


def make_answer_from_snippets(question: str, snippets: List[str]) -> str:
    if not snippets:
        return "I couldn’t find an answer in the documents."
    best = snippets[0].strip()
    if len(snippets) > 1:
        second = snippets[1].strip()
        return f"{best}\n\n{second}"
    return best


def query_rag(question: str, top_k: int = 3) -> Dict[str, Any]:
    t0 = time.perf_counter()

    q = (question or "").strip()
    if not q:
        return {"status": "error", "message": "Question is empty.", "answer": "", "citations": []}

    client = get_client()
    collection = get_collection(client)

    res = collection.query(
        query_texts=[q],
        n_results=int(top_k or 3),
        include=["documents", "metadatas", "distances"],
    )
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
