from __future__ import annotations

from pathlib import Path

import yaml

from scripts.gate14_node_lifecycle import summarize_traffic, validate_node_loss_recovery, validate_placement


ROOT = Path(__file__).resolve().parents[1]


def _documents() -> list[dict]:
    return list(yaml.safe_load_all(Path("deploy/operations/gate14-workload.yaml").read_text(encoding="utf-8")))


def test_pdb_requires_one_available_replica() -> None:
    pdb = yaml.safe_load(Path("deploy/operations/gate14-pdb.yaml").read_text(encoding="utf-8"))
    assert pdb["kind"] == "PodDisruptionBudget"
    assert pdb["spec"]["minAvailable"] == 1
    assert pdb["spec"]["selector"]["matchLabels"] == {"app": "agenttrust-gate14"}


def test_workload_spreads_replicas_and_preserves_security() -> None:
    deployment = _documents()[0]
    spec = deployment["spec"]
    pod = spec["template"]["spec"]
    container = pod["containers"][0]
    assert spec["replicas"] == 2
    anti = pod["affinity"]["podAntiAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"][0]
    assert anti["topologyKey"] == "kubernetes.io/hostname"
    assert container["readinessProbe"]["httpGet"]["path"] == "/healthz"
    assert container["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert container["resources"]["requests"] and container["resources"]["limits"]
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


def test_placement_validation_requires_separate_ready_nodes() -> None:
    pods = [
        {"name": "a", "node": "worker-a", "phase": "Running", "ready": True},
        {"name": "b", "node": "worker-b", "phase": "Running", "ready": True},
    ]
    result = validate_placement(pods)
    assert result["distributed"] is True
    assert result["nodes"] == ["worker-a", "worker-b"]


def test_traffic_metrics_capture_failure_window() -> None:
    records = [
        {"ok": True, "latency_ms": 10.0, "timestamp": "2026-01-01T00:00:00Z"},
        {"ok": False, "latency_ms": 50.0, "timestamp": "2026-01-01T00:00:01Z"},
        {"ok": False, "latency_ms": 55.0, "timestamp": "2026-01-01T00:00:03Z"},
        {"ok": True, "latency_ms": 12.0, "timestamp": "2026-01-01T00:00:04Z"},
    ]
    summary = summarize_traffic(records, records[0]["timestamp"], records[-1]["timestamp"])
    assert summary["total_requests"] == 4
    assert summary["successful_requests"] == 2
    assert summary["failed_requests"] == 2
    assert summary["maximum_consecutive_failures"] == 2
    assert summary["disruption_duration_seconds"] == 2.0
    assert summary["zero_failed_requests"] is False


def test_service_continuity_result_is_machine_readable() -> None:
    summary = summarize_traffic(
        [{"ok": True, "latency_ms": 2.0, "timestamp": "2026-01-01T00:00:00Z"}],
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:01Z",
    )
    assert summary["zero_failed_requests"] is True
    assert summary["p50_latency_ms"] == 2.0
    assert summary["p95_latency_ms"] == 2.0


def test_unplanned_node_loss_requires_survivor_and_rejoin() -> None:
    baseline = {
        "items": [
            {"metadata": {"name": "worker-a"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
            {"metadata": {"name": "worker-b"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
        ]
    }
    during_loss = {
        "items": [
            {"metadata": {"name": "worker-a"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
        ]
    }
    recovered = baseline
    report = validate_node_loss_recovery(baseline, during_loss, recovered, "worker-b")
    assert report["service_continuity"] is True
    assert report["node_rejoin"] is True
    assert report["recovery_validated"] is True


def test_unplanned_node_loss_rejects_no_survivor() -> None:
    snapshot = {"items": [{"metadata": {"name": "worker-b"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}]}
    try:
        validate_node_loss_recovery(snapshot, {"items": []}, snapshot, "worker-b")
    except AssertionError as exc:
        assert "no baseline worker remained ready" in str(exc)
    else:
        raise AssertionError("node-loss validation must fail closed without a surviving worker")


def test_gate14_workflow_executes_bounded_node_loss_recovery() -> None:
    workflow = (ROOT / ".github/workflows/gate14-node-lifecycle-ops.yml").read_text(encoding="utf-8")
    assert "docker stop" in workflow
    assert "kubectl delete node" in workflow
    assert "docker start" in workflow
    assert "node-loss-report" in workflow
    assert "UNPLANNED_NODE_LOSS: NOT_EXECUTED" not in workflow
