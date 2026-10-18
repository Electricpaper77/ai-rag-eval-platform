"""Minimal AgentTrust IQ inference service for the Gate 1 runtime workload."""

from fastapi import FastAPI
from backend.app.inference import handle_chat_completions_async

app = FastAPI(title="AgentTrust IQ Gate 1 inference")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "agenttrust-iq", "status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(payload: dict) -> dict:
    return await handle_chat_completions_async(payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
