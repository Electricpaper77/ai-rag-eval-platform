from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def _docs(name: str) -> list[dict]:
    return [item for item in yaml.safe_load_all((ROOT / "deploy" / "scheduling" / name).read_text()) if item]


def test_quota_and_limitrange_are_real_namespace_admission_controls() -> None:
    quotas = _docs("gate15-resourcequotas.yaml")
    limits = _docs("gate15-limitrange.yaml")
    assert {item["kind"] for item in quotas} == {"ResourceQuota"}
    assert {item["metadata"]["namespace"] for item in quotas} == {"tenant-standard", "tenant-priority"}
    assert all(item["spec"]["hard"].get("pods") for item in quotas)
    assert all(item["spec"]["limits"][0]["defaultRequest"] for item in limits)
    assert all(item["spec"]["limits"][0]["max"] for item in limits)


def test_workloads_preserve_runtime_security_and_real_inference() -> None:
    deployments = [item for item in _docs("gate15-workloads.yaml") if item["kind"] == "Deployment"]
    assert len(deployments) == 2
    for deployment in deployments:
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        assert container["command"] == ["python", "-m", "scripts.gate1_inference"]
        assert container["readinessProbe"]["httpGet"]["path"] == "/healthz"
        assert container["livenessProbe"]["httpGet"]["path"] == "/healthz"
        assert pod["automountServiceAccountToken"] is False
        assert pod["securityContext"] == {
            "runAsNonRoot": True,
            "runAsUser": 10001,
            "runAsGroup": 10001,
            "seccompProfile": {"type": "RuntimeDefault"},
        }
        assert container["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        }
        assert container["resources"]["requests"] and container["resources"]["limits"]
        assert container["imagePullPolicy"] == "Never"


def test_placement_and_policy_controls_are_explicit() -> None:
    deployments = [item for item in _docs("gate15-workloads.yaml") if item["kind"] == "Deployment"]
    standard = deployments[0]["spec"]["template"]["spec"]
    priority = deployments[1]["spec"]["template"]["spec"]
    assert standard["topologySpreadConstraints"][0]["whenUnsatisfiable"] == "DoNotSchedule"
    assert standard["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
    assert priority["nodeSelector"] == {"agenttrust.io/workload-tier": "priority"}
    assert priority["tolerations"][0]["key"] == "dedicated"
    policies = _docs("gate15-networkpolicy.yaml")
    assert len(policies) == 2
    assert all(set(policy["spec"]["policyTypes"]) == {"Ingress", "Egress"} for policy in policies)


def test_priority_classes_are_non_system_and_preempt_lower_priority() -> None:
    priorities = _docs("gate15-priorityclasses.yaml")
    assert {item["metadata"]["name"] for item in priorities} == {"agenttrust-standard", "agenttrust-critical"}
    assert all(item.get("preemptionPolicy") == "PreemptLowerPriority" for item in priorities)
    assert all(item["value"] > 0 for item in priorities)
