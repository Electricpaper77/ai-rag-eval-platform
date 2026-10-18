from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


CHART = Path(__file__).resolve().parents[1] / "deploy" / "helm" / "agenttrust"
HELM = shutil.which("helm")


def _render(*set_values: str) -> list[dict]:
    if HELM is None:
        pytest.skip("helm is required for Gate 3 chart assertions")
    result = subprocess.run(
        [HELM, "template", "agenttrust", str(CHART), *sum((["--set", value] for value in set_values), [])],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def _resource(resources: list[dict], kind: str) -> dict:
    return next(resource for resource in resources if resource["kind"] == kind)


def _container(resources: list[dict]) -> dict:
    deployment = _resource(resources, "Deployment")
    return deployment["spec"]["template"]["spec"]["containers"][0]


def test_default_chart_renders_secure_inference_resources() -> None:
    resources = _render()
    assert _resource(resources, "Deployment")
    assert _resource(resources, "Service")
    assert _resource(resources, "NetworkPolicy")
    assert not any(resource["kind"] == "PersistentVolumeClaim" for resource in resources)

    deployment = _resource(resources, "Deployment")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = _container(resources)
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["securityContext"] == {
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
    assert container["readinessProbe"]["httpGet"]["path"] == "/healthz"
    assert container["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert {mount["mountPath"] for mount in container["volumeMounts"]} >= {"/tmp"}
    env = {item["name"]: item["value"] for item in container["env"]}
    assert env["INFERENCE_ARTIFACTS_ROOT"].startswith("/tmp/")
    assert env["INFERENCE_LOG_PATH"].startswith("/tmp/")
    assert "amd.com/gpu" not in container["resources"]["limits"]


def test_gpu_and_pvc_values_render_deterministically() -> None:
    gpu_resources = _render("gpu.count=2", "gpu.resourceKey=amd.com/gpu")
    gpu_container = _container(gpu_resources)
    assert gpu_container["resources"]["limits"]["amd.com/gpu"] == "2"

    pvc_resources = _render("persistence.enabled=true", "persistence.size=2Gi", "persistence.storageClass=standard")
    pvc = _resource(pvc_resources, "PersistentVolumeClaim")
    assert pvc["spec"]["resources"]["requests"]["storage"] == "2Gi"
    assert pvc["spec"]["storageClassName"] == "standard"


def test_network_policy_can_be_disabled_without_changing_deployment_security() -> None:
    resources = _render("networkPolicy.enabled=false")
    assert not any(resource["kind"] == "NetworkPolicy" for resource in resources)
    assert _container(resources)["securityContext"]["readOnlyRootFilesystem"] is True
