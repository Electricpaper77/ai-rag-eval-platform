from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest

from backend.app.workload_platform import LocalWorkloadExecutor, build_workload, network_policy


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
    assert policy["spec"]["ingress"] == [] and policy["spec"]["egress"] == []


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
