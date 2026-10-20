"""Run one lightweight real AgentTrust HTTP smoke test."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen


def request_json(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, float, dict]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=payload, method=method, headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    with urlopen(request, timeout=10) as response:
        status = response.status
        result = json.loads(response.read().decode("utf-8"))
    return status, (time.perf_counter() - started) * 1000, result


def run(base_url: str) -> dict:
    health_status, health_ms, health = request_json(f"{base_url}/healthz")
    chat_status, chat_ms, chat = request_json(
        f"{base_url}/v1/chat/completions",
        "POST",
        {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Return one short portfolio smoke response."}], "max_tokens": 16},
    )
    if health_status != 200 or chat_status != 200:
        raise RuntimeError(f"unexpected status health={health_status} chat={chat_status}")
    if not isinstance(chat.get("choices"), list) or not chat["choices"] or "message" not in chat["choices"][0]:
        raise RuntimeError("chat response is not OpenAI-compatible")
    return {"health": {"status": health_status, "latency_ms": round(health_ms, 3), "schema": sorted(health)}, "chat": {"status": chat_status, "latency_ms": round(chat_ms, 3), "schema_valid": True, "response_id": chat.get("id")}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--output", default="artifacts/gate18/smoke.json")
    args = parser.parse_args()
    try:
        result = run(args.base_url.rstrip("/"))
    except Exception as exc:
        print(f"PORTFOLIO_SMOKE: FAIL: {exc}")
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print("PORTFOLIO_SMOKE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
