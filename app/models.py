from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RoutingPolicy = Literal[
    "lowest_latency",
    "lowest_cost",
    "highest_quality",
    "fallback_on_error",
    "weighted_round_robin",
]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] | str
    content: str


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage]
    temperature: float | None = 0.7
    max_tokens: int | None = 256
    stream: bool | None = False
    routing_policy: RoutingPolicy = "fallback_on_error"
    user: str | None = None


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage
    backend: str
    routing_policy: str


class BackendHealth(BaseModel):
    backend: str
    healthy: bool
    circuit_open: bool
    error_count: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    backends: list[BackendHealth]


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]


class EvaluationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model_response: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    risk_category: Literal["hallucination", "pii", "prompt_injection", "citation", "refusal"]
    metadata: dict[str, Any] | None = None


class EvaluationResponse(BaseModel):
    pass_: bool = Field(alias="pass")
    score: float = Field(ge=0.0, le=1.0)
    failure_reasons: list[str]
    metrics: dict[str, float]
    run_id: str
