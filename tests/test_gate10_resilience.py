from __future__ import annotations

import json
from pathlib import Path

import yaml

from backend.app.resilience.controller import FaultInjectionDisabled, ResilienceController
from backend.app.resilience.error_budget import calculate_error_budget
from scripts.gate10_resilience_scorecard import score


ROOT = Path(__file__).resolve().parents[1]


def _docs(path: str) -> list[dict]:
    return [item for item in yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8")) if item]


def test_fault_injection_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GATE10_ENABLE_FAULTS", raising=False)
    controller = ResilienceController()
    assert controller.status()["enabled"] is False
    try:
        controller.inject("latency")
    except FaultInjectionDisabled:
        pass
    else:
        raise AssertionError("fault injection must be disabled by default")


def test_fault_types_are_validated_and_duration_is_bounded(monkeypatch):
    monkeypatch.setenv("GATE10_ENABLE_FAULTS", "true")
    controller = ResilienceController()
    state = controller.inject("latency", duration_seconds=999)
    assert state["fault_type"] == "latency"
    assert state["duration_seconds"] == controller.MAX_DURATION_SECONDS
    assert controller.status()["active"]["detected_state"] == "injected"
    assert controller.recover()["recovered"] is True
    try:
        controller.inject("not-a-real-fault")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown faults must be rejected")


def test_error_budget_math_is_labeled_ci_only():
    result = calculate_error_budget(100, 2)
    assert result.name == "CI resilience error budget"
    assert result.observed_availability == 0.98
    assert result.allowable_failures == 1
    assert result.budget_consumed_percent == 100.0


def test_scorecard_requires_detection_continuity_and_recovery():
    passed = score([{"experiment": "pod-delete", "detected": True, "service_continuity": True, "recovered": True}])
    held = score([{"experiment": "latency", "detected": True, "service_continuity": True, "recovered": False}])
    assert passed["resilience"] == "PASS"
    assert held["resilience"] == "HOLD"


def test_chaos_manifest_and_rbac_are_bounded_and_secure():
    experiments = _docs("deploy/chaos/gate10-experiments.yaml")[0]["spec"]["experiments"]
    assert {item["faultType"] for item in experiments} == {
        "pod_delete", "dependency_unavailable", "latency", "http_5xx", "readiness_failure", "network_denial"
    }
    assert all(0 < item["durationSeconds"] <= 120 for item in experiments)
    docs = _docs("deploy/chaos/gate10.yaml")
    deployments = [item for item in docs if item.get("kind") == "Deployment"]
    assert {item["metadata"]["name"] for item in deployments} == {"gate10-serving", "gate10-dependency"}
    for deployment in deployments:
        pod = deployment["spec"]["template"]["spec"]
        assert pod["securityContext"]["runAsNonRoot"] is True
        assert pod["securityContext"]["runAsUser"] == 10001
        assert pod["securityContext"]["runAsGroup"] == 10001
        assert pod["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
        container = pod["containers"][0]
        assert container["securityContext"]["readOnlyRootFilesystem"] is True
        assert container["securityContext"]["allowPrivilegeEscalation"] is False
        assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
        assert container["resources"]["requests"] and container["resources"]["limits"]
    rbac = _docs("deploy/chaos/gate10-rbac.yaml")
    assert all(item["kind"] != "ClusterRole" for item in rbac)
    role = next(item for item in rbac if item["kind"] == "Role")
    assert {verb for rule in role["rules"] for verb in rule["verbs"]} <= {"get", "list", "watch", "delete", "patch", "update", "create"}


def test_scorecard_output_is_machine_readable():
    result = score([{"experiment": "dependency", "detected": True, "service_continuity": True, "recovered": True, "budget_consumed": 10}])
    json.dumps(result)
