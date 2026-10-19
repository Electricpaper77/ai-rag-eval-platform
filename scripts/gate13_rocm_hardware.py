"""Strict Gate 13 AMD ROCm hardware proof.

This module is deliberately different from the CPU-safe Gate 6 probe.  It
never converts a missing device into a passing result and never falls back to
CPU execution.  A successful result requires an AMD ROCm device, the device
nodes, HIP-enabled PyTorch, a synchronized tensor operation, and a small real
model inference.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.app.gpu_runtime import detect_rocm_runtime


class HardwareUnavailable(RuntimeError):
    """Raised when the host cannot provide the required AMD hardware proof."""


def _run(command: Sequence[str], *, timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return {"command": list(command), "returncode": 127, "stdout": "", "stderr": str(exc)}
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def collect_host_evidence(output_dir: Path) -> dict[str, Any]:
    """Save immutable host/ROCm command output and return command metadata."""

    output_dir.mkdir(parents=True, exist_ok=True)
    commands = {
        "uname": ["uname", "-a"],
        "lspci": ["lspci", "-nn"],
        "rocminfo": ["rocminfo"],
        "rocm_smi": ["rocm-smi", "--showproductname", "--json"],
        "hipconfig": ["hipconfig", "--full"],
        "device_nodes": ["ls", "-l", "/dev/kfd", "/dev/dri"],
    }
    evidence: dict[str, Any] = {}
    for name, command in commands.items():
        result = _run(command)
        evidence[name] = result
        (output_dir / f"{name}.stdout").write_text(result["stdout"], encoding="utf-8")
        (output_dir / f"{name}.stderr").write_text(result["stderr"], encoding="utf-8")
    return evidence


def validate_hardware_status(status: Mapping[str, Any], device_paths: Sequence[str]) -> None:
    """Reject every status that cannot prove a usable AMD ROCm device."""

    required_paths = {"/dev/kfd", "/dev/dri"}
    if status.get("vendor") != "AMD":
        raise HardwareUnavailable("ROCm did not report an AMD GPU")
    if int(status.get("device_count", 0)) < 1:
        raise HardwareUnavailable("ROCm reported no AMD GPU agents")
    if not status.get("rocm_available") or not status.get("hip_available"):
        raise HardwareUnavailable("ROCm/HIP runtime is unavailable")
    missing = sorted(required_paths.difference(device_paths))
    if missing:
        raise HardwareUnavailable(f"required device nodes are missing: {', '.join(missing)}")


def _torch_rocm_proof() -> dict[str, Any]:
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - hardware environment only
        raise HardwareUnavailable(f"PyTorch is unavailable: {exc}") from exc

    hip_version = getattr(getattr(torch, "version", None), "hip", None)
    if not hip_version:
        raise HardwareUnavailable("PyTorch is not a HIP/ROCm build")
    if not torch.cuda.is_available():
        raise HardwareUnavailable("PyTorch reports no ROCm device")

    device = torch.device("cuda:0")
    device_name = torch.cuda.get_device_name(device)
    left = torch.tensor([1.0, 2.0, 3.0], device=device)
    right = torch.tensor([4.0, 5.0, 6.0], device=device)
    result = left + right
    torch.cuda.synchronize(device)
    values = result.cpu().tolist()
    if values != [5.0, 7.0, 9.0]:
        raise RuntimeError(f"unexpected synchronized GPU result: {values}")

    return {
        "torch_version": torch.__version__,
        "torch_hip_version": hip_version,
        "cuda_api_device": str(device),
        "device_name": device_name,
        "device_count": torch.cuda.device_count(),
        "vector_result": values,
        "synchronized": True,
    }


def _model_inference() -> dict[str, Any]:
    import torch  # type: ignore

    torch.manual_seed(13)
    device = torch.device("cuda:0")
    model = torch.nn.Sequential(
        torch.nn.Linear(32, 64),
        torch.nn.ReLU(),
        torch.nn.Linear(64, 8),
    ).to(device)
    model.eval()
    inputs = torch.ones((4, 32), device=device)
    torch.cuda.reset_peak_memory_stats(device)
    with torch.inference_mode():
        started = time.perf_counter()
        output = model(inputs)
        torch.cuda.synchronize(device)
        elapsed_ms = (time.perf_counter() - started) * 1000
    values = output.detach().cpu().tolist()
    return {
        "model": "torch.nn.Sequential(32-64-8)",
        "device": str(device),
        "device_name": torch.cuda.get_device_name(device),
        "output_shape": list(output.shape),
        "output_checksum": float(output.detach().sum().cpu().item()),
        "output_sample": values[0][:3],
        "latency_ms": elapsed_ms,
        "peak_memory_allocated_bytes": torch.cuda.max_memory_allocated(device),
        "synchronized": True,
    }


def execute(output_dir: Path) -> dict[str, Any]:
    """Run strict hardware, compute, and model proofs and persist JSON evidence."""

    command_evidence = collect_host_evidence(output_dir)
    device_paths = [path for path in ("/dev/kfd", "/dev/dri") if Path(path).exists()]
    status = detect_rocm_runtime()
    validate_hardware_status(status, device_paths)
    torch_proof = _torch_rocm_proof()
    model = _model_inference()
    evidence = {
        "status": "AMD_HARDWARE: EXECUTED",
        "host": {"system": platform.platform(), "python": sys.version},
        "runtime": status,
        "device_paths": device_paths,
        "pytorch_rocm": torch_proof,
        "model_inference": model,
        "commands": command_evidence,
    }
    (output_dir / "hardware-proof.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/gate13"))
    args = parser.parse_args(argv)
    try:
        evidence = execute(args.output_dir)
    except HardwareUnavailable as exc:
        print(f"Gate 13: BLOCKED — AMD HARDWARE UNAVAILABLE: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - hardware environment only
        print(f"AMD_HARDWARE: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, indent=2, sort_keys=True))
    print("AMD_HARDWARE: EXECUTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
