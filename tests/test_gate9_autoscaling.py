from __future__ import annotations

import json
from pathlib import Path

import yaml
from prometheus_client import generate_latest

from backend.app.capacity import CapacityController, capacity_recommendation, capacity_status


ROOT = Path(__file__).resolve().parents[1]


def _documents(path: str) -> list[dict]:
    return [doc for doc in yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8")) if doc]


def test_capacity_recommendation_reason_codes_are_deterministic():
    controller = CapacityController(capacity_per_replica=2, queue_capacity=1)
    assert controller.recommendation()["reason_code"] == "LOW_UTILIZATION_STABLE"
    controller._active = 2
    assert controller.recommendation()["reason_code"] == "ACTIVE_CAPACITY_OR_QUEUE_PRESSURE"
    controller._queued = 1
    assert controller.recommendation()["reason_code"] == "QUEUE_FULL_AND_ACTIVE_CAPACITY_FULL"


def test_capacity_exhaustion_is_bounded_and_structured():
    controller = CapacityController(capacity_per_replica=1, queue_capacity=0)
    controller._active = 1
    assert controller.recommendation()["recommendation"] == "capacity_exhausted"
    assert controller.recommendation()["reason_code"] == "QUEUE_FULL_AND_ACTIVE_CAPACITY_FULL"


def test_capacity_endpoints_and_required_metrics_exist():
    assert capacity_status()["reason_code"]
    assert capacity_recommendation()["reason_code"]
    metrics = generate_latest().decode("utf-8")
    for name in (
        "agenttrust_active_requests",
        "agenttrust_queued_requests",
        "agenttrust_capacity_per_replica",
        "agenttrust_saturation_ratio",
        "agenttrust_scaling_recommendation",
        "agenttrust_backpressure_total",
    ):
        assert name in metrics


def test_gate9_workload_preserves_runtime_security_and_limits():
    docs = _documents("deploy/autoscaling/gate9.yaml")
    deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]
    assert {doc["metadata"]["name"] for doc in deployments} == {"gate9-serving", "gate9-queue-scaler"}
    for deployment in deployments:
        pod = deployment["spec"]["template"]["spec"]
        assert pod["securityContext"] == {
            "runAsNonRoot": True,
            "runAsUser": 10001,
            "runAsGroup": 10001,
            "seccompProfile": {"type": "RuntimeDefault"},
        }
        container = pod["containers"][0]
        security = container["securityContext"]
        assert security["allowPrivilegeEscalation"] is False
        assert security["readOnlyRootFilesystem"] is True
        assert security["capabilities"]["drop"] == ["ALL"]
        assert container["resources"]["requests"] and container["resources"]["limits"]
    assert [doc for doc in docs if doc.get("kind") == "ServiceAccount"][0]["metadata"]["name"] == "gate9-queue-scaler"


def test_hpa_is_bounded_and_has_cpu_stabilization():
    hpa = _documents("deploy/autoscaling/gate9-hpa.yaml")[0]
    assert hpa["apiVersion"] == "autoscaling/v2"
    assert hpa["spec"]["minReplicas"] == 1 and hpa["spec"]["maxReplicas"] == 4
    assert hpa["spec"]["metrics"][0]["resource"]["name"] == "cpu"
    assert hpa["spec"]["behavior"]["scaleDown"]["stabilizationWindowSeconds"] >= 30


def test_network_policy_and_observability_assets_are_real():
    docs = _documents("deploy/autoscaling/gate9.yaml")
    policies = [doc for doc in docs if doc.get("kind") == "NetworkPolicy"]
    assert {policy["metadata"]["name"] for policy in policies} == {"gate9-serving-policy", "gate9-queue-scaler-policy"}
    serving = next(policy for policy in policies if policy["metadata"]["name"] == "gate9-serving-policy")
    assert serving["spec"]["ingress"][0]["from"][0]["podSelector"]["matchLabels"]["app.kubernetes.io/part-of"] == "agenttrust-iq"
    alerts = yaml.safe_load((ROOT / "deploy/observability/gate9-alerts.yaml").read_text(encoding="utf-8"))
    assert {rule["alert"] for rule in alerts["groups"][0]["rules"]} == {"AgentTrustCapacitySaturated", "AgentTrustScalingStuck"}
    json.loads((ROOT / "deploy/observability/gate9-dashboard.json").read_text(encoding="utf-8"))
