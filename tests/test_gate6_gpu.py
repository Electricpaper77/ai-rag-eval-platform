from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.app import gpu_runtime
from gpu_platform.scheduler_mapping import (
    kubernetes_gpu_request,
    scheduler_mapping,
    slurm_gpu_request,
    validate_gpu_count,
)


def test_cpu_only_detection_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpu_runtime.shutil, "which", lambda _name: None)
    status = gpu_runtime.detect_rocm_runtime(device_paths=())
    assert status == {
        "vendor": None,
        "rocm_available": False,
        "hip_available": False,
        "device_count": 0,
        "devices": [],
        "driver_version": None,
        "runtime_version": None,
        "evidence_source": [],
    }


def test_missing_rocm_binary_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpu_runtime.shutil, "which", lambda _name: None)
    status = gpu_runtime.detect_gpu_runtime(env={"ROCR_VISIBLE_DEVICES": ""}, device_paths=())
    assert status["device_count"] == 0
    assert status["rocm_available"] is False


def test_rocminfo_parser_extracts_multiple_gpu_agents() -> None:
    output = """
Agent 1
  Name: CPU
  Device Type: CPU
Agent 2
  Name: gfx942
  Marketing Name: AMD Instinct MI300X
  Device Type: GPU
Agent 3
  Name: gfx1100
  Marketing Name: AMD Radeon PRO
  Device Type: GPU
"""
    devices = gpu_runtime.parse_rocminfo_output(output)
    assert [device["name"] for device in devices] == ["AMD Instinct MI300X", "AMD Radeon PRO"]
    assert [device["architecture"] for device in devices] == ["gfx942", "gfx1100"]


def test_rocm_detection_uses_structured_command_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    binaries = {"rocminfo": "/fake/rocminfo", "rocm-smi": "/fake/rocm-smi", "hipcc": "/fake/hipcc"}
    monkeypatch.setattr(gpu_runtime.shutil, "which", lambda name: binaries.get(name))

    def runner(command: list[str] | tuple[str, ...]) -> tuple[int, str, str]:
        if command[0].endswith("rocminfo"):
            return 0, "Agent 1\n Name: gfx942\n Marketing Name: MI300X\n Device Type: GPU\n", ""
        if command[0].endswith("rocm-smi"):
            return 0, "{}", "ROCm version: 6.2.0"
        return 0, "HIP version: 6.2.0", ""

    status = gpu_runtime.detect_rocm_runtime(command_runner=runner, device_paths=())
    assert status["vendor"] == "AMD"
    assert status["device_count"] == 1
    assert status["hip_available"] is True
    assert "rocminfo" in status["evidence_source"]


def test_gpu_status_endpoint_returns_cpu_safe_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpu_runtime.shutil, "which", lambda _name: None)
    payload = gpu_runtime.gpu_runtime_status()
    assert payload["device_count"] == 0
    assert payload["rocm_available"] is False


@pytest.mark.parametrize("count", [-1, 9, True, "1"])
def test_invalid_gpu_counts_are_rejected(count: object) -> None:
    with pytest.raises(ValueError):
        validate_gpu_count(count)  # type: ignore[arg-type]


def test_scheduler_mapping_preserves_gpu_count() -> None:
    assert kubernetes_gpu_request(0) == {}
    assert slurm_gpu_request(0) == []
    assert kubernetes_gpu_request(2) == {"amd.com/gpu": "2"}
    assert slurm_gpu_request(2) == ["--gres", "gpu:2"]
    assert scheduler_mapping(3)["gpu_count"] == 3
    assert scheduler_mapping(3)["kubernetes"] == {"amd.com/gpu": "3"}
    assert scheduler_mapping(3)["slurm"] == ["--gres", "gpu:3"]
    assert scheduler_mapping(3)["integrated"] is False


def test_amd_device_plugin_reference_is_pinned_and_cpu_workflow_does_not_apply_it() -> None:
    reference = Path("deploy/gpu/amd/device-plugin.yaml")
    documents = list(yaml.safe_load_all(reference.read_text(encoding="utf-8")))
    data = documents[0]["data"]
    assert data["sourceRevision"] == "dea1db1"
    assert data["expectedResource"] == "amd.com/gpu"
    workflow = Path(".github/workflows/gate6-amd-rocm-hpc.yml").read_text(encoding="utf-8")
    assert "kubectl apply -f deploy/gpu/amd" not in workflow


def test_amd_values_are_declarative_and_request_amd_resource() -> None:
    values = yaml.safe_load(Path("deploy/helm/agenttrust/values-amd-gpu.yaml").read_text(encoding="utf-8"))
    assert values["gpu"] == {"count": 1, "resourceKey": "amd.com/gpu"}
    assert values["nodeSelector"]["agenttrust.ai/accelerator"] == "amd-gpu"
    assert "declarative" in Path("deploy/helm/agenttrust/values-amd-gpu.yaml").read_text(encoding="utf-8").lower()
