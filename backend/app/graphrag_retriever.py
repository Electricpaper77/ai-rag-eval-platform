from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .rag import get_client, get_collection

GRAPH_INDEX_PATH = Path(os.getenv("GRAPHRAG_INDEX_PATH", "artifacts/graphrag_graph.json"))

_GRAPH: Dict[str, Any] = {"nodes": {}, "edges": defaultdict(dict)}


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[A-Za-z0-9_]+", (text or "").lower()) if len(t) > 2}


def _extract_entities(text: str) -> set[str]:
    """Extract entities with spaCy when available, otherwise regex fallback."""
    raw = text or ""
    entities: set[str] = set()

    try:
        import spacy  # type: ignore

        nlp = spacy.load("en_core_web_sm")
        doc = nlp(raw)
        entities = {ent.text.strip() for ent in doc.ents if ent.text.strip()}
        if entities:
            return entities
    except Exception:
        pass

    # Regex fallback: proper nouns and acronyms.
    patterns = re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b|\b[A-Z]{2,}\b", raw)
    entities = {p.strip() for p in patterns if p.strip()}
    return entities


def _jaccard_score(a: Iterable[str], b: Iterable[str]) -> float:
    aa, bb = set(a), set(b)
    if not aa and not bb:
        return 0.0
    inter = len(aa & bb)
    union = len(aa | bb)
    return inter / union if union else 0.0


def _edge_weight(doc_a: Dict[str, Any], doc_b: Dict[str, Any]) -> tuple[float, str | None]:
    entities_a = set(doc_a.get("entities") or [])
    entities_b = set(doc_b.get("entities") or [])
    entity_overlap = entities_a & entities_b
    semantic = _jaccard_score(doc_a.get("tokens") or set(), doc_b.get("tokens") or set())
    entity_score = 0.25 * len(entity_overlap)
    weight = semantic + entity_score
    reason = "shared_entities" if entity_overlap else ("semantic_similarity" if semantic > 0 else None)
    return weight, reason


def build_graph_index(documents: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a lightweight graph where nodes are chunks and edges are entity/similarity links."""
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    normalized_docs: List[Dict[str, Any]] = []
    for i, doc in enumerate(documents):
        text = (doc.get("text") or doc.get("document") or "").strip()
        if not text:
            continue
        doc_id = str(doc.get("id") or f"doc-{i}")
        source = doc.get("source") or (doc.get("metadata") or {}).get("source")
        chunk = doc.get("chunk") or (doc.get("metadata") or {}).get("chunk")
        entities = sorted(_extract_entities(text))
        tokens = _tokenize(text)
        node = {
            "id": doc_id,
            "text": text,
            "source": source,
            "chunk": chunk,
            "entities": entities,
            "tokens": sorted(tokens),
        }
        nodes[doc_id] = node
        normalized_docs.append(node)

    for i, left in enumerate(normalized_docs):
        for right in normalized_docs[i + 1 :]:
            weight, reason = _edge_weight(left, right)
            if weight <= 0:
                continue
            edges[left["id"]][right["id"]] = {"weight": weight, "reason": reason}
            edges[right["id"]][left["id"]] = {"weight": weight, "reason": reason}

    serializable = {"nodes": nodes, "edges": {k: v for k, v in edges.items()}}
    GRAPH_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_INDEX_PATH.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")

    _GRAPH["nodes"] = nodes
    _GRAPH["edges"] = defaultdict(dict, {k: dict(v) for k, v in edges.items()})
    return serializable


def _ensure_graph_loaded() -> Dict[str, Any]:
    if _GRAPH.get("nodes"):
        return _GRAPH
    if GRAPH_INDEX_PATH.exists():
        data = json.loads(GRAPH_INDEX_PATH.read_text(encoding="utf-8"))
        _GRAPH["nodes"] = data.get("nodes", {})
        _GRAPH["edges"] = defaultdict(dict, data.get("edges", {}))
    return _GRAPH


def graph_expand(results: Sequence[Dict[str, Any]], depth: int = 1) -> List[Dict[str, Any]]:
    graph = _ensure_graph_loaded()
    nodes = graph.get("nodes", {})
    edges = graph.get("edges", {})

    expanded: Dict[str, Dict[str, Any]] = {}
    frontier = [(r.get("id"), 0, r.get("score", 1.0)) for r in results if r.get("id")]

    for item in results:
        if item.get("id"):
            expanded[item["id"]] = dict(item)

    while frontier:
        node_id, level, parent_score = frontier.pop(0)
        if node_id not in edges or level >= depth:
            continue
        for neighbor_id, edge_meta in edges[node_id].items():
            node = nodes.get(neighbor_id)
            if not node:
                continue
            score = parent_score * float(edge_meta.get("weight", 0))
            existing = expanded.get(neighbor_id)
            if existing is None or score > existing.get("score", 0):
                expanded[neighbor_id] = {
                    "id": neighbor_id,
                    "document": node.get("text", ""),
                    "metadata": {"source": node.get("source"), "chunk": node.get("chunk")},
                    "score": score,
                    "from_graph": True,
                    "edge_reason": edge_meta.get("reason"),
                }
            frontier.append((neighbor_id, level + 1, max(score, 0.0001)))

    return list(expanded.values())


def _convert_vector_results(res: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    distances = (res.get("distances") or [[]])[0]

    results: List[Dict[str, Any]] = []
    for i in range(min(len(ids), len(docs), len(metas), len(distances))):
        dist = float(distances[i])
        score = 1.0 / (1.0 + max(dist, 0.0))
        results.append(
            {
                "id": str(ids[i]),
                "document": docs[i],
                "metadata": metas[i],
                "distance": dist,
                "score": score,
                "from_graph": False,
            }
        )
    return results


def _rerank(query: str, items: Sequence[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    query_tokens = _tokenize(query)
    ranked = []
    for item in items:
        doc = item.get("document") or ""
        lexical = _jaccard_score(query_tokens, _tokenize(doc))
        base = float(item.get("score", 0.0))
        item["final_score"] = (0.7 * base) + (0.3 * lexical)
        ranked.append(item)
    ranked.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    return ranked[:k]


def hybrid_retrieve(query: str, k: int = 5) -> Dict[str, Any]:
    t0 = time.perf_counter()
    client = get_client()
    collection = get_collection(client)

    vector_response = collection.query(
        query_texts=[query],
        n_results=max(k, 1),
        include=["documents", "metadatas", "distances"],
    )
    vector_results = _convert_vector_results(vector_response)
    expanded = graph_expand(vector_results, depth=1)
    ranked = _rerank(query, expanded, k)

    citations = [
        {
            "rank": i + 1,
            "id": item.get("id"),
            "source": (item.get("metadata") or {}).get("source"),
            "chunk": (item.get("metadata") or {}).get("chunk"),
            "snippet": (item.get("document") or "")[:240],
            "from_graph": bool(item.get("from_graph")),
            "score": round(float(item.get("final_score", 0.0)), 4),
        }
        for i, item in enumerate(ranked)
    ]

    latency_ms = (time.perf_counter() - t0) * 1000.0
    answer = "\n\n".join([(r.get("document") or "").strip() for r in ranked[:2] if r.get("document")]).strip()
    if not answer:
        answer = "I couldn’t find an answer in the documents."

    return {
        "status": "ok",
        "query": query,
        "answer": answer,
        "citations": citations,
        "num_citations": len(citations),
        "latency_ms": latency_ms,
        "vector_seed_count": len(vector_results),
        "expanded_count": max(0, len(expanded) - len(vector_results)),
    }


def build_graph_index_from_collection() -> Dict[str, Any]:
    client = get_client()
    collection = get_collection(client)
    payload = collection.get(include=["documents", "metadatas"])

    ids = payload.get("ids") or []
    docs = payload.get("documents") or []
    metas = payload.get("metadatas") or []

    documents = [
        {
            "id": str(ids[i]),
            "text": docs[i],
            "metadata": metas[i] or {},
            "source": (metas[i] or {}).get("source"),
            "chunk": (metas[i] or {}).get("chunk"),
        }
        for i in range(min(len(ids), len(docs), len(metas)))
    ]
    return build_graph_index(documents)
