"""Standalone Gate 8 HTTP router process."""

import uvicorn
from fastapi import FastAPI

from backend.app.serving.router import router


app = FastAPI(title="AgentTrust Gate 8 canary router")
app.include_router(router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ready"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
