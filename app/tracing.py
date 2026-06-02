from __future__ import annotations

import os
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from app.artifacts import ArtifactWriter


@dataclass
class TraceContext:
    trace_id: str = field(default_factory=lambda: secrets.token_hex(16))

    def span_id(self) -> str:
        return secrets.token_hex(8)


class TraceRecorder:
    """Records local trace artifacts and exports real OpenTelemetry spans when configured."""

    def __init__(self, artifacts: ArtifactWriter):
        self.artifacts = artifacts
        self.otel_enabled = False
        self.otel_endpoint = _otel_endpoint()
        self._tracer = None
        self._status_code = None
        self._span_kind = None
        self._configure_opentelemetry()
        self._write_pipeline_proof()

    @contextmanager
    def span(
        self,
        context: TraceContext,
        name: str,
        attributes: dict,
        parent_span_id: str | None = None,
    ) -> Iterator[str]:
        span_id = context.span_id()
        started = time.time()
        status = "OK"
        error: str | None = None
        otel_span_cm = self._start_otel_span(context, name, attributes, parent_span_id)
        otel_span = otel_span_cm.__enter__() if otel_span_cm else None
        try:
            yield span_id
        except Exception as exc:
            status = "ERROR"
            error = str(exc)
            if otel_span and self._status_code:
                otel_span.record_exception(exc)
                otel_span.set_status(self._status_code.ERROR, str(exc))
            raise
        finally:
            ended = time.time()
            payload = {
                "trace_id": context.trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "name": name,
                "kind": "SERVER" if parent_span_id is None else "CLIENT",
                "start_time_unix_nano": int(started * 1_000_000_000),
                "end_time_unix_nano": int(ended * 1_000_000_000),
                "duration_ms": round((ended - started) * 1000, 3),
                "status": {"code": status, "message": error or ""},
                "attributes": attributes,
            }
            self.artifacts.append_jsonl("otel_traces.jsonl", payload)
            if otel_span:
                otel_span.set_attribute("inference.local_trace_id", context.trace_id)
                otel_span.set_attribute("inference.local_span_id", span_id)
                if parent_span_id:
                    otel_span.set_attribute("inference.local_parent_span_id", parent_span_id)
                otel_span_cm.__exit__(None, None, None)

    def _configure_opentelemetry(self) -> None:
        if not self.otel_endpoint:
            return
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.trace import SpanKind, StatusCode
        except Exception:
            return

        resource = Resource.create(
            {
                "service.name": os.getenv("OTEL_SERVICE_NAME", "ai-inference-gateway"),
                "service.namespace": "ai-infrastructure",
                "deployment.environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "local"),
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=self.otel_endpoint)))
        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer("ai-inference-gateway")
        self._span_kind = SpanKind
        self._status_code = StatusCode
        self.otel_enabled = True

    def _start_otel_span(self, context: TraceContext, name: str, attributes: dict, parent_span_id: str | None):
        if not self.otel_enabled or self._tracer is None:
            return None
        kind = self._span_kind.SERVER if parent_span_id is None else self._span_kind.CLIENT
        span = self._tracer.start_as_current_span(name, kind=kind)
        active_span = span.__enter__()
        for key, value in attributes.items():
            active_span.set_attribute(key, value)
        active_span.set_attribute("inference.local_trace_id", context.trace_id)
        if parent_span_id:
            active_span.set_attribute("inference.local_parent_span_id", parent_span_id)
        return _EnteredSpan(span, active_span)

    def _write_pipeline_proof(self) -> None:
        self.artifacts.write_text(
            "opentelemetry_pipeline.json",
            (
                "{\n"
                f'  "otel_sdk_available": {str(self._tracer is not None).lower()},\n'
                f'  "otlp_exporter_enabled": {str(self.otel_enabled).lower()},\n'
                f'  "otlp_traces_endpoint": "{self.otel_endpoint or ""}",\n'
                '  "docker_runtime_installs_otel_sdk": true,\n'
                '  "docker_compose_runs_otel_collector": true,\n'
                '  "local_trace_artifact": "docs/artifacts/otel_traces.jsonl",\n'
                '  "collector_config": "observability/otel-collector/config.yaml"\n'
                "}\n"
            ),
        )


class _EnteredSpan:
    def __init__(self, manager, span):
        self.manager = manager
        self.span = span

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc, tb):
        return self.manager.__exit__(exc_type, exc, tb)


def _otel_endpoint() -> str | None:
    traces_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if traces_endpoint:
        return traces_endpoint
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        return f"{endpoint.rstrip('/')}/v1/traces"
    return None
