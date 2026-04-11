from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.app import graphrag_retriever
from backend.app.main import app


client = TestClient(app)


def test_build_graph_index_and_expand_neighbors(tmp_path, monkeypatch):
    monkeypatch.setattr(graphrag_retriever, "GRAPH_INDEX_PATH", tmp_path / "graph.json")

    docs = [
        {"id": "1", "text": "OpenAI released GPT in San Francisco.", "source": "a.txt", "chunk": 0},
        {"id": "2", "text": "San Francisco teams use AI in products.", "source": "b.txt", "chunk": 0},
        {"id": "3", "text": "Completely unrelated gardening tips.", "source": "c.txt", "chunk": 0},
    ]
    graph = graphrag_retriever.build_graph_index(docs)

    assert "1" in graph["nodes"]
    assert "2" in graph["edges"]["1"]

    expanded = graphrag_retriever.graph_expand(
        [{"id": "1", "document": docs[0]["text"], "metadata": {"source": "a.txt", "chunk": 0}, "score": 1.0}],
        depth=1,
    )
    ids = {item["id"] for item in expanded}
    assert "1" in ids
    assert "2" in ids


def test_evaluate_graphrag_reports_precision_grounding_and_latency_delta(tmp_path, monkeypatch):
    log_path = tmp_path / "graphrag_eval.jsonl"

    def fake_baseline(prompt: str, top_k: int = 5):
        return {
            "answer": "baseline",
            "citations": [{"source": "policy.md", "snippet": "refund policy overview"}],
            "latency_ms": 5,
        }

    def fake_hybrid(prompt: str, k: int = 5):
        return {
            "answer": "hybrid",
            "citations": [
                {"source": "policy.md", "snippet": "refund policy for annual plans", "from_graph": False},
                {"source": "faq.md", "snippet": "related cancellation and billing", "from_graph": True},
            ],
            "latency_ms": 7,
        }

    monkeypatch.setattr("backend.app.main.query_rag", fake_baseline)
    monkeypatch.setattr("backend.app.main.hybrid_retrieve", fake_hybrid)
    monkeypatch.setattr("backend.app.main.build_graph_index_from_collection", lambda: {"nodes": {}, "edges": {}})

    def fake_append(payload):
        log_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return str(log_path)

    monkeypatch.setattr("backend.app.main._append_graphrag_eval_log", fake_append)

    response = client.post("/evaluate_graphrag", json={"prompt": "refund policy", "top_k": 2, "depth": 1})
    assert response.status_code == 200

    data = response.json()
    eval_data = data["evaluation"]

    assert "retrieval_precision_baseline" in eval_data
    assert "retrieval_precision_hybrid" in eval_data
    assert "citation_grounding_improvement" in eval_data
    assert "latency_delta_ms" in eval_data

    assert Path(data["log_path"]).exists()
