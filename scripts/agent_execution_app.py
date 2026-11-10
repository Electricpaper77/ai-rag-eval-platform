"""ASGI entry point that recovers durable Agent Execution audits on startup."""

from backend.app.agent_execution import CancellationController
from backend.app.main import app


app.state.agent_execution_cancellation = CancellationController()
