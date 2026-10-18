from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from backend.app.workload_platform import LocalWorkloadExecutor, WorkloadRequest, build_workload, build_workload_request, network_policy, validate_workload, workload_types
from scripts.gate2_render import render_objects


@pytest.mark.parametrize("kind,expected", [("dev-pod", "Pod"), ("ci-job", "Job"), ("benchmark-job", "Job"), ("inference-service", "Deployment")])
def test_builds_all_workload_classes(kind, expected):
    objects = build_workload("demo", kind)
    assert objects[0]["kind"] == expected
    spec = objects[0]["spec"]
    pod_spec = spec["template"]["spec"] if "template" in spec else spec
    container = pod_spec["containers"][0]
    assert container["securityContext"]["runAsNonRoot"] is True
    assert container["resources"]["limits"]
    assert pod_spec["automountServiceAccountToken"] is False


def test_rejects_unknown_kind_and_denies_network_by_default():
    with pytest.raises(ValueError):
        build_workload("demo", "gpu-shell")
    policy = network_policy("demo")
    assert policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert policy["spec"]["egress"][0]["ports"][0]["port"] == 53


def test_admission_and_types_are_deterministic():
    assert workload_types()["workload_types"] == ["dev-pod", "ci-job", "inference-service", "benchmark-job"]
    denied = validate_workload(WorkloadRequest(name="demo", workload_type="unknown"))
    assert denied["admission_decision"] == "deny"
    assert "unsupported_workload_type" in denied["reason_codes"]


def test_gpu_pvc_and_inference_controls():
    request = WorkloadRequest(name="infer", workload_type="inference-service", gpu_count=1, pvc_size="1Gi", node_selector={"accelerator": "amd"}, replicas=2)
    objects = build_workload_request(request)
    deployment = next(item for item in objects if item["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["resources"]["limits"]["amd.com/gpu"] == "1"
    assert container["readinessProbe"]["httpGet"]["path"] == "/healthz"
    assert deployment["spec"]["replicas"] == 2
    assert any(item["kind"] == "PersistentVolumeClaim" for item in objects)


@pytest.mark.parametrize("field,value,reason", [
    ("cpu_request", "bad", "invalid_cpu_request"),
    ("cpu_limit", "bad", "invalid_cpu_limit"),
    ("memory_request", "1G", "invalid_memory_request"),
    ("memory_limit", "1G", "invalid_memory_limit"),
])
def test_resource_quantity_reason_codes(field, value, reason):
    payload = {"name": "demo", "workload_type": "ci-job", field: value}
    result = validate_workload(WorkloadRequest(**payload))
    assert result["admission_decision"] == "deny"
    assert reason in result["reason_codes"]


def test_resource_order_scheduling_and_gpu_admission():
    result = validate_workload(WorkloadRequest(name="demo", workload_type="ci-job", cpu_request="2", cpu_limit="1", memory_request="1Gi", memory_limit="512Mi", node_selector={"bad key": "x"}, tolerations=[{"effect": "bad"}]))
    assert result["admission_decision"] == "deny"
    assert {"cpu_request_exceeds_limit", "memory_request_exceeds_limit", "invalid_node_selector", "invalid_toleration"}.issubset(result["reason_codes"])
    no_gpu = build_workload_request(WorkloadRequest(name="nogpu", workload_type="ci-job"))[0]["spec"]["template"]["spec"]["containers"][0]
    assert "amd.com/gpu" not in no_gpu["resources"]["limits"]


def test_benchmark_command_is_executable_and_writable():
    objects = build_workload_request(WorkloadRequest(name="bench", workload_type="benchmark-job"))
    container = objects[0]["spec"]["template"]["spec"]["containers"][0]
    assert container["command"] == ["python", "-m", "scripts.gate2_benchmark"]
    assert {mount["mountPath"] for mount in container["volumeMounts"]} == {"/tmp"}


def test_gate2_renderer_uses_kind_image_and_pull_policy():
    objects = render_objects()
    containers = []
    for item in objects:
        spec = item.get("spec", {})
        pod_spec = spec.get("template", {}).get("spec", spec)
        containers.extend(pod_spec.get("containers", []))
    assert len(containers) == 4
    assert {container["image"] for container in containers} == {"agenttrust-iq:gate2"}
    assert {container["imagePullPolicy"] for container in containers} == {"Never"}


def test_benchmark_success_and_cleanup(tmp_path: Path):
    executor = LocalWorkloadExecutor(tmp_path, lambda q, k: {"answer": q, "citations": ["local"], "usage": {"total_tokens": 1}})
    result = executor.run_benchmark("success")
    assert result["overall"]["total_cases"] == 9
    assert (tmp_path / "regression_success.jsonl").exists()
    assert executor.cleanup("success") is True


def test_benchmark_failure_is_recorded_and_cleanup_is_idempotent(tmp_path: Path):
    def failing(_q, _k):
        raise RuntimeError("synthetic runtime failure")
    executor = LocalWorkloadExecutor(tmp_path, failing)
    result = executor.run_benchmark("failure")
    assert result["overall"]["refusal_rate"] == 1.0
    assert executor.cleanup("failure") is True
    assert executor.cleanup("failure") is False
