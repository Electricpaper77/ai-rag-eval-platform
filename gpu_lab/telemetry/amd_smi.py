"""Best-effort, offline-testable AMD SMI JSON normalization."""
from __future__ import annotations
import json, shutil, subprocess, time
from typing import Any, Callable

FIELDS = {"gpu_name": ("gpu_name", "name", "product_name", "card_series"), "gpu_utilization_percent": ("gpu_utilization", "gpu_use", "gfx_activity"), "memory_utilization_percent": ("memory_utilization", "mem_use", "memory_activity"), "vram_used_mb": ("vram_used", "used_vram", "memory_used"), "vram_total_mb": ("vram_total", "total_vram", "memory_total"), "power_watts": ("power", "average_socket_power", "power_watts"), "gpu_temperature_celsius": ("temperature", "edge_temperature", "gpu_temperature"), "memory_temperature_celsius": ("memory_temperature", "mem_temperature"), "gpu_clock_mhz": ("gpu_clock", "gfx_clock", "sclk"), "memory_clock_mhz": ("memory_clock", "mem_clock", "mclk")}

def _number(value: Any) -> float | None:
    if value is None: return None
    try: return float(str(value).replace("%", "").replace("MiB", "").replace("MB", "").replace("MHz", "").replace("W", "").strip())
    except (TypeError, ValueError): return None
def _find(data: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in data: return data[key]
    return None
def _devices(payload: Any) -> list[dict]:
    if isinstance(payload, list): return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict): return []
    for key in ("gpus", "GPUs", "devices", "gpu", "card"):
        value=payload.get(key)
        if isinstance(value, list): return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict): return list(value.values()) if all(isinstance(x,dict) for x in value.values()) else [value]
    return [payload]

def normalize(payload: Any, timestamp: float | None = None) -> list[dict]:
    result=[]
    for index, raw in enumerate(_devices(payload)):
        flat=dict(raw); flat.update(raw.get("metrics", {}) if isinstance(raw.get("metrics"),dict) else {})
        row={"timestamp": timestamp, "device_index": int(_find(flat,("device_index","index","gpu")) or index), "verified_gpu_name": _find(flat,FIELDS["gpu_name"])}
        for name, keys in FIELDS.items():
            if name == "gpu_name": continue
            row[name]=_number(_find(flat,keys))
        result.append(row)
    return result

def sanitize_error(error: str) -> str:
    lowered=error.lower()
    if "permission" in lowered or "access is denied" in lowered: return "amd-smi permission denied"
    return "amd-smi unavailable" if "not found" in lowered else error[:160]

class AmdSmiTelemetry:
    def __init__(self, which: Callable[[str], str | None] = shutil.which, run: Callable[..., Any] = subprocess.run): self.which,self.run=which,run
    def capabilities(self) -> dict:
        binary=self.which("amd-smi")
        if not binary: return {"telemetry_status":"unavailable","reason":"amd-smi not installed","amd_smi_version":None}
        try:
            output=self.run([binary,"version"],capture_output=True,text=True,timeout=5,check=False)
            return {"telemetry_status":"available","amd_smi_version":(output.stdout or "").strip()[:200] or None}
        except Exception as exc: return {"telemetry_status":"unavailable","reason":sanitize_error(str(exc)),"amd_smi_version":None}
    def sample(self) -> tuple[list[dict], dict]:
        binary=self.which("amd-smi")
        if not binary: return [], {"telemetry_status":"unavailable","reason":"amd-smi not installed"}
        try:
            output=self.run([binary,"metric","--json"],capture_output=True,text=True,timeout=5,check=False)
            if output.returncode: return [], {"telemetry_status":"unavailable","reason":sanitize_error(output.stderr or output.stdout)}
            return normalize(json.loads(output.stdout), time.time()), {"telemetry_status":"available"}
        except json.JSONDecodeError: return [], {"telemetry_status":"unavailable","reason":"amd-smi returned malformed JSON"}
        except Exception as exc: return [], {"telemetry_status":"unavailable","reason":sanitize_error(str(exc))}
