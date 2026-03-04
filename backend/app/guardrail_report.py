import json, os, time, hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

RUNS_DIR = os.getenv("RUNS_DIR", "/tmp/runs")
RUNS_DIR = os.path.normpath(RUNS_DIR)
RUNS_DIR = os.getenv("RUNS_DIR", "/tmp/runs")
RUNS_DIR = os.path.normpath(RUNS_DIR)

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def _hash_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]

def new_report(question: str) -> Dict[str, Any]:
    return {
        "timestamp": _now_iso(),
        "request_id": f"gr_{int(time.time()*1000)}_{_hash_text(question)}",
        "input_hash": _hash_text(question),
        "question_preview": (question or "")[:120],
        "decision": "allow",
        "reasons": [],
        "pii_redacted": False,
        "pii_types": [],
        "injection_detected": False,
        "injection_reason": None,
        "latency_ms": None,
        "cpu_percent": None,
        "memory_mb": None,
    }

def finalize_and_save(report: Dict[str, Any]) -> str:
    os.makedirs(RUNS_DIR, exist_ok=True)
    fname = f"guardrail_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    path = os.path.join(RUNS_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    return path
