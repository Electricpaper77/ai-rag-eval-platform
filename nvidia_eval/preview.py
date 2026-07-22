"""Local preview fallback for the NVIDIA router when optional RAG dependencies are unavailable."""
from fastapi import FastAPI
from backend.app.routes.nvidia_evaluation import router
app=FastAPI(title="AgentTrust IQ")
app.include_router(router)
