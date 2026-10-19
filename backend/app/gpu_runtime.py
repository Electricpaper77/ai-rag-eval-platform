"""Safe, evidence-backed AMD GPU/ROCm runtime detection.

The detector is deliberately best effort.  It never invents a device, driver,
or version when ROCm is not installed, which makes it safe to call from CPU
development environments and ordinary CI runners.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from fastapi import APIRouter


CommandRunner = Callable[[Sequence[str]], tuple[int, str, str]]


def _default_runner(command: Sequence[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def _first_value(text: str, patterns: Sequence[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip().strip('"')
            if value:
                return value
    return None


def parse_rocminfo_output(text: str) -> list[dict[str, Any]]:
    """Extract AMD GPU agents from human-readable ``rocminfo`` output."""

    devices: list[dict[str, Any]] = []
    blocks = re.split(r"(?=^\s*Agent\s+\d+\s*$)", text, flags=re.IGNORECASE | re.MULTILINE)
    for block in blocks:
        if not re.search(r"Device Type:\s*GPU|Device Type:\s*GPU", block, re.IGNORECASE):
            continue
        name = _first_value(block, (r"Marketing Name:\s*(.+)", r"Name:\s*(.+)"))
        architecture = _first_value(block, (r"Name:\s*(gfx[\w.-]+)", r"ISA Info:\s*([^\r\n]+)"))
        devices.append(
            {
                "id": len(devices),
                "name": name or "AMD GPU",
                "architecture": architecture,
                "vendor": "AMD",
                "evidence_source": "rocminfo",
            }
        )
    return devices


def parse_rocm_smi_output(text: str) -> list[dict[str, Any]]:
    """Extract devices from JSON or common tabular ``rocm-smi`` output."""

    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        payload = None

    if isinstance(payload, dict):
        rows: list[Any] = []
        for key, value in payload.items():
            if re.search(r"card\d+|gpu\d+|device", str(key), re.IGNORECASE):
                rows.append((key, value))
        devices: list[dict[str, Any]] = []
        for key, value in rows:
            data = value if isinstance(value, dict) else {"value": value}
            name = next(
                (data.get(field) for field in ("Card series", "Card model", "GPU[0]", "Product Name") if data.get(field)),
                None,
            )
            devices.append(
                {
                    "id": len(devices),
                    "name": str(name or key),
                    "vendor": "AMD",
                    "evidence_source": "rocm-smi",
                }
            )
        if devices:
            return devices

    devices = []
    for line in text.splitlines():
        match = re.search(r"(?:GPU|card)\s*([0-9]+).*?(?:model|name|series)\s*[:=]\s*(.+)$", line, re.IGNORECASE)
        if match:
            devices.append(
                {
                    "id": int(match.group(1)),
                    "name": match.group(2).strip(),
                    "vendor": "AMD",
                    "evidence_source": "rocm-smi",
                }
            )
    return devices


def _hip_available(env: Mapping[str, str], command_runner: CommandRunner) -> tuple[bool, str | None]:
    hipcc = shutil.which("hipcc")
    if hipcc:
        code, stdout, _ = command_runner([hipcc, "--version"])
        if code == 0:
            return True, _first_value(stdout, (r"HIP version:\s*([\w.-]+)", r"HIP version\s*([\w.-]+)"))
    for candidate in (
        env.get("HIP_PATH", ""),
        "/opt/rocm/lib/libamdhip64.so",
        "/opt/rocm/lib/libamdhip64.so.6",
    ):
        if candidate and Path(candidate).exists():
            return True, None
    return False, None


def detect_rocm_runtime(
    *,
    env: Mapping[str, str] | None = None,
    command_runner: CommandRunner | None = None,
    device_paths: Sequence[str] = ("/dev/kfd", "/dev/dri"),
) -> dict[str, Any]:
    """Return a JSON-serializable ROCm/GPU status without fabricating values."""

    environment = dict(os.environ if env is None else env)
    runner = command_runner or _default_runner
    evidence: list[str] = []
    rocminfo_output = ""
    rocm_smi_output = ""
    rocm_available = False
    rocm_command_succeeded = False
    runtime_version: str | None = None
    driver_version: str | None = None

    rocminfo = shutil.which("rocminfo")
    if rocminfo:
        code, stdout, stderr = runner([rocminfo])
        if code == 0:
            rocm_command_succeeded = True
            rocminfo_output = stdout
            rocminfo_text = f"{stdout}\n{stderr}"
            rocminfo_version = _first_value(rocminfo_text, (r"ROCm version:\s*([\w.-]+)", r"Runtime Version:\s*([\w.-]+)"))
            runtime_version = rocminfo_version or runtime_version
            rocminfo_devices = parse_rocminfo_output(stdout)
            if rocminfo_devices:
                evidence.append("rocminfo")
                rocminfo_output = stdout
                rocminfo_devices_result = rocminfo_devices
            else:
                rocminfo_devices_result = []
        else:
            rocminfo_devices_result = []
    else:
        rocminfo_devices_result = []

    rocm_smi = shutil.which("rocm-smi")
    if rocm_smi:
        code, stdout, stderr = runner([rocm_smi, "--showproductname", "--json"])
        if code == 0:
            rocm_command_succeeded = True
            rocm_smi_output = stdout
            rocm_smi_devices = parse_rocm_smi_output(stdout)
            if rocm_smi_devices:
                evidence.append("rocm-smi")
                rocm_smi_output = stdout
            else:
                rocm_smi_devices = []
            smi_text = f"{stdout}\n{stderr}"
            driver_version = _first_value(smi_text, (r"Driver version\s*[:=]\s*([\w.-]+)", r"ROCm version\s*[:=]\s*([\w.-]+)"))
            runtime_version = runtime_version or _first_value(smi_text, (r"ROCm version\s*[:=]\s*([\w.-]+)",))
        else:
            rocm_smi_devices = []
    else:
        rocm_smi_devices = []

    devices = rocminfo_devices_result or rocm_smi_devices
    device_nodes = [path for path in device_paths if Path(path).exists()]
    rocm_device_nodes = [path for path in device_nodes if path.endswith("/kfd") or path == "/dev/kfd"]
    if rocm_device_nodes:
        evidence.extend(f"device:{path}" for path in rocm_device_nodes)
        if "/dev/dri" in device_nodes:
            evidence.append("device:/dev/dri")
    hip_available, hip_version = _hip_available(environment, runner)
    rocm_available = rocm_command_succeeded or bool(rocm_device_nodes)
    if hip_version and not runtime_version:
        runtime_version = hip_version

    visible = environment.get("ROCR_VISIBLE_DEVICES") or environment.get("HIP_VISIBLE_DEVICES")
    if visible is not None and visible.strip() == "":
        devices = []
    elif visible and devices:
        selected: list[dict[str, Any]] = []
        for token in (item.strip() for item in visible.split(",")):
            if token.isdigit() and int(token) < len(devices):
                selected.append(devices[int(token)])
        if selected:
            devices = selected

    if devices:
        for device in devices:
            device.setdefault("vendor", "AMD")

    return {
        "vendor": "AMD" if devices or rocm_command_succeeded or rocm_device_nodes else None,
        "rocm_available": rocm_available,
        "hip_available": hip_available,
        "device_count": len(devices),
        "devices": devices,
        "driver_version": driver_version,
        "runtime_version": runtime_version,
        "evidence_source": evidence,
    }


def detect_gpu_runtime(**kwargs: Any) -> dict[str, Any]:
    """Stable public alias for callers that do not need ROCm-specific naming."""

    return detect_rocm_runtime(**kwargs)


router = APIRouter(prefix="/platform/gpu", tags=["gpu-runtime"])


@router.get("/status")
def gpu_runtime_status() -> dict[str, Any]:
    return detect_rocm_runtime()
