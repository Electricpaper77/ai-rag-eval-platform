from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

SHADOW_LOG_PATH = Path("artifacts/shadow_runs/shadow_eval.jsonl")
SHADOW_SUMMARY_PATH = Path("artifacts/proof/shadow_eval_summary.json")

_COST_PER_1K_TOKENS: dict[str, float] = {
    "openai": 0.005,
    "vllm": 0.001,
    "mock": 0.0,
}

_FILE_LOCK = Lock()
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shadow-eval")


def _now_iso8601() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def _extract_prompt(messages: list[dict[str, Any]]) -> str:
    return "\n".join(str(message.get("content", "")).strip() for message in messages if message.get("content"))


def _simulated_response(model: str, prompt: str) -> str:
    last_line = prompt.splitlines()[-1] if prompt else ""
    return f"[{model}] {last_line[:120]}".strip()


def _append_jsonl(row: dict[str, Any], log_path: Path | None = None) -> None:
    path = log_path or SHADOW_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with _FILE_LOCK:
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(row) + "\n")


def record_shadow_log(row: dict[str, Any], log_path: Path | None = None) -> None:
    _append_jsonl(row=row, log_path=log_path)


def run_shadow_evaluation_async(
    *,
    request_id: str,
    primary_model: str,
    shadow_model: str,
    messages: list[dict[str, Any]],
    primary_response: str,
    primary_latency_ms: float,
    shadow_latency_ms: float,
    log_path: Path | None = None,
) -> None:
    prompt = _extract_prompt(messages)
    prompt_tokens = _estimate_tokens(prompt)

    def _job() -> None:
        shadow_response = _simulated_response(shadow_model, prompt)
        completion_tokens = max(_estimate_tokens(primary_response), _estimate_tokens(shadow_response))
        row = {
            "request_id": request_id,
            "timestamp": _now_iso8601(),
            "primary_model": primary_model,
            "shadow_model": shadow_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "primary_latency_ms": round(float(primary_latency_ms), 2),
            "shadow_latency_ms": round(float(shadow_latency_ms), 2),
            "primary_response": primary_response,
            "shadow_response": shadow_response,
        }
        record_shadow_log(row, log_path=log_path)

    _EXECUTOR.submit(_job)


def load_shadow_summary(log_path: Path | None = None) -> dict[str, float]:
    path = log_path or SHADOW_LOG_PATH
    if not path.exists():
        return {"agreement_rate": 0.0, "avg_latency_delta_ms": 0.0, "avg_cost_delta": 0.0}

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

    if not rows:
        return {"agreement_rate": 0.0, "avg_latency_delta_ms": 0.0, "avg_cost_delta": 0.0}

    agreements = 0
    latency_deltas: list[float] = []
    cost_deltas: list[float] = []

    for row in rows:
        primary_response = str(row.get("primary_response", "")).strip().lower()
        shadow_response = str(row.get("shadow_response", "")).strip().lower()
        if primary_response == shadow_response:
            agreements += 1

        primary_latency = float(row.get("primary_latency_ms", 0.0))
        shadow_latency = float(row.get("shadow_latency_ms", 0.0))
        latency_deltas.append(shadow_latency - primary_latency)

        prompt_tokens = int(row.get("prompt_tokens", 0))
        completion_tokens = int(row.get("completion_tokens", 0))
        total_tokens = max(prompt_tokens + completion_tokens, 1)
        primary_model = str(row.get("primary_model", ""))
        shadow_model = str(row.get("shadow_model", ""))

        primary_cost = (_COST_PER_1K_TOKENS.get(primary_model, 0.0) * total_tokens) / 1000
        shadow_cost = (_COST_PER_1K_TOKENS.get(shadow_model, 0.0) * total_tokens) / 1000
        cost_deltas.append(round(shadow_cost - primary_cost, 6))

    return {
        "agreement_rate": round(agreements / len(rows), 4),
        "avg_latency_delta_ms": round(sum(latency_deltas) / len(latency_deltas), 2),
        "avg_cost_delta": round(sum(cost_deltas) / len(cost_deltas), 6),
    }


def write_shadow_summary(
    *,
    log_path: Path | None = None,
    summary_path: Path | None = None,
) -> dict[str, float]:
    summary = load_shadow_summary(log_path=log_path)
    output_path = summary_path or SHADOW_SUMMARY_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
