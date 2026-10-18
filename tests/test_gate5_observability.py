from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from prometheus_client import generate_latest
from backend.app.metrics import INFERENCE_ERRORS_TOTAL

from scripts.gate1_inference import app, gate5_force_errors_enabled


ROOT = Path(__file__).resolve().parents[1]


def _metric_value(payload: str, metric: str, labels: str = "") -> float:
    pattern = rf"^{re.escape(metric)}(?:\{{{re.escape(labels)}\}})?\s+([0-9.eE+-]+)$"
    for line in payload.splitlines():
        match = re.match(pattern, line)
        if match:
            return float(match.group(1))
    return 0.0


def _metrics_text() -> str:
    return generate_latest().decode("utf-8")


def test_metrics_endpoint_exposes_runtime_metrics() -> None:
    assert "/metrics" in {getattr(route, "path", "") for route in app.routes}
    response = _metrics_text()
    required = {
        "http_requests_total",
        "http_request_duration_seconds",
        "http_requests_in_flight",
        "healthz_requests_total",
        "inference_requests_total",
        "inference_errors_total",
    }
    assert all(name in response for name in required)


def test_failure_mode_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GATE5_FORCE_ERRORS", raising=False)
    assert gate5_force_errors_enabled() is False


def test_failure_mode_causes_measurable_500s_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GATE5_FORCE_ERRORS", raising=False)
    before = _metrics_text()
    assert gate5_force_errors_enabled() is False
    monkeypatch.setenv("GATE5_FORCE_ERRORS", "true")
    assert gate5_force_errors_enabled() is True
    INFERENCE_ERRORS_TOTAL.labels(reason="gate5_forced_error").inc()
    after = _metrics_text()
    labels = 'reason="gate5_forced_error"'
    assert _metric_value(after, "inference_errors_total", labels) > _metric_value(before, "inference_errors_total", labels)


def test_observability_values_render_metrics_and_environment() -> None:
    helm = __import__("shutil").which("helm")
    if helm is None:
        pytest.skip("helm is required for Gate 5 chart assertions")
    import subprocess

    rendered = subprocess.run(
        [helm, "template", "agenttrust", str(ROOT / "deploy/helm/agenttrust"), "--set", "observability.metrics.enabled=true", "--set", "env.GATE5_FORCE_ERRORS=true"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    resources = [item for item in yaml.safe_load_all(rendered) if item]
    service = next(item for item in resources if item["kind"] == "Service")
    deployment = next(item for item in resources if item["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert service["metadata"]["annotations"]["prometheus.io/path"] == "/metrics"
    assert service["metadata"]["annotations"]["prometheus.io/port"] == "8080"
    assert {item["name"]: item["value"] for item in container["env"]}["GATE5_FORCE_ERRORS"] == "true"
    assert container["securityContext"]["readOnlyRootFilesystem"] is True


def test_rules_dashboard_and_slo_are_valid() -> None:
    rules = yaml.safe_load((ROOT / "deploy/observability/prometheus/alerting_rules.yaml").read_text(encoding="utf-8"))
    alert_names = {rule["alert"] for group in rules["groups"] for rule in group["rules"]}
    assert alert_names == {"AgentTrustHighErrorRate", "AgentTrustHighLatency", "AgentTrustUnavailable"}
    dashboard = json.loads((ROOT / "deploy/observability/grafana/agenttrust-dashboard.json").read_text(encoding="utf-8"))
    assert dashboard["title"] == "AgentTrust Observability SLO"
    assert {panel["title"] for panel in dashboard["panels"]} >= {
        "Request rate", "Error rate", "p50 latency", "p95 latency", "Inference requests", "Inference errors"
    }
    slo = yaml.safe_load((ROOT / "deploy/observability/slo/agenttrust-slo.yaml").read_text(encoding="utf-8"))
    assert slo["spec"]["availability"]["objective"] == 0.99
    assert slo["spec"]["errorRate"]["objective"] == 0.01
    assert slo["spec"]["latency"]["objectiveSeconds"] == 1.0
