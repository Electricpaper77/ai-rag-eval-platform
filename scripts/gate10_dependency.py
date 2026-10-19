"""Minimal real dependency used by Gate 10 outage experiments."""

from fastapi import FastAPI

app = FastAPI(title="Gate 10 dependency")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8081)
