from pathlib import Path

import yaml

from scripts.gate16_resource_diagnostics import (
    build_diagnostics,
    classify_failure,
    cpu_throttle_delta,
    parse_cgroup_version,
    parse_cpu_stat,
    parse_oom_status,
    summarize_traffic,
)


ROOT = Path(__file__).parents[1]


def test_cgroup_and_cpu_counter_parsers() -> None:
    assert parse_cgroup_version("cgroup on /sys/fs/cgroup type cgroup2") == "v2"
    before = parse_cpu_stat("usage_usec 10\nnr_periods 4\nnr_throttled 1\nthrottled_usec 20\n")
    after = parse_cpu_stat("usage_usec 20\nnr_periods 8\nnr_throttled 3\nthrottled_usec 80\n")
    assert cpu_throttle_delta(before, after) == {"nr_periods": 4, "nr_throttled": 2, "throttled_usec": 60}


def test_oom_parsing_and_failure_classification() -> None:
    pod = {"status": {"phase": "Failed", "containerStatuses": [{"state": {"terminated": {"reason": "OOMKilled", "exitCode": 137}}}]}}
    assert parse_oom_status(pod)["oom_killed"] is True
    assert classify_failure(pod) == "OOMKilled"
    assert classify_failure({"status": {"phase": "Pending"}}, "0/3 nodes are available: Insufficient cpu") == "Unschedulable"


def test_traffic_metrics_are_deterministic() -> None:
    result = summarize_traffic(
        [{"ok": True, "latency_ms": 10}, {"ok": False, "latency_ms": 30}, {"ok": True, "latency_ms": 20}],
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:03Z",
    )
    assert result["total_requests"] == 3
    assert result["successful_requests"] == 2
    assert result["failed_requests"] == 1
    assert result["p95_latency_ms"] == 20.0
    assert result["maximum_consecutive_failures"] == 1


def test_live_workload_manifest_preserves_security_and_limits() -> None:
    docs = list(yaml.safe_load_all((ROOT / "deploy/resource-pressure/gate16-workload.yaml").read_text()))
    deployment = docs[0]
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert container["command"] == ["python", "-m", "scripts.gate1_inference"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"] == {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001, "seccompProfile": {"type": "RuntimeDefault"}}
    assert container["securityContext"] == {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}}
    assert container["resources"]["requests"] and container["resources"]["limits"]
    assert container["readinessProbe"]["httpGet"]["path"] == "/healthz"


def test_diagnostic_report_uses_observed_inputs(tmp_path: Path) -> None:
    oom = tmp_path / "oom.json"
    oom.write_text('{"status":{"containerStatuses":[{"state":{"terminated":{"reason":"OOMKilled","exitCode":137}}}]}}')
    pending = tmp_path / "pending.txt"
    pending.write_text("0/3 nodes are available: Insufficient cpu")
    before = tmp_path / "before.txt"
    before.write_text("nr_periods 1\nnr_throttled 0\n")
    after = tmp_path / "after.txt"
    after.write_text("nr_periods 2\nnr_throttled 1\n")
    report = build_diagnostics(str(oom), str(pending), None, str(before), str(after))
    assert report["failures"]["oom"]["oom_killed"] is True
    assert report["failures"]["scheduler"] == "Unschedulable"
    assert report["failures"]["cpu"] == "CPUThrottled"
