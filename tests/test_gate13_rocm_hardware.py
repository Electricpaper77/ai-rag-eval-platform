from __future__ import annotations

from pathlib import Path

import pytest

from scripts.gate13_rocm_hardware import HardwareUnavailable, validate_hardware_status


def test_gate13_rejects_cpu_only_status() -> None:
    with pytest.raises(HardwareUnavailable, match="AMD GPU"):
        validate_hardware_status(
            {"vendor": None, "device_count": 0, "rocm_available": False, "hip_available": False},
            (),
        )


def test_gate13_requires_both_rocm_device_nodes() -> None:
    status = {"vendor": "AMD", "device_count": 1, "rocm_available": True, "hip_available": True}
    with pytest.raises(HardwareUnavailable, match="/dev/dri"):
        validate_hardware_status(status, ("/dev/kfd",))


def test_gate13_sources_have_no_cpu_fallback_and_emit_strict_status() -> None:
    source = Path("scripts/gate13_rocm_hardware.py").read_text(encoding="utf-8")
    assert "torch.cuda.is_available()" in source
    assert "torch.cuda.synchronize" in source
    assert "AMD_HARDWARE: EXECUTED" in source
    assert "AMD_HARDWARE: NOT_EXECUTED" not in source


def test_gate13_workflow_requires_amd_self_hosted_runner() -> None:
    workflow = Path(".github/workflows/gate13-amd-rocm-hardware.yml").read_text(encoding="utf-8")
    assert "self-hosted" in workflow
    assert "amd-gpu" in workflow
    assert "ubuntu-latest" not in workflow
    assert "gate13-amd-rocm-hardware-evidence" in workflow
    assert "torch.cuda.is_available" in workflow
