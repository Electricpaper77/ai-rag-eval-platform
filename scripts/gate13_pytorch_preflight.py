"""Strict PyTorch ROCm qualification; CPU-only execution is not accepted."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def qualify() -> dict[str, Any]:
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - runner-only path
        raise RuntimeError(f"PyTorch import failed: {exc}") from exc

    assert torch.version.hip, "torch.version.hip is empty; a ROCm build is required"
    assert torch.cuda.is_available(), "PyTorch cannot see a ROCm device"
    device_count = torch.cuda.device_count()
    assert device_count >= 1, "no ROCm devices are visible"

    device = torch.device("cuda:0")
    left = torch.tensor([1.0, 2.0, 3.0], device=device)
    right = torch.tensor([4.0, 5.0, 6.0], device=device)
    result = left + right
    torch.cuda.synchronize(device)
    values = result.cpu().tolist()
    assert values == [5.0, 7.0, 9.0], f"unexpected synchronized result: {values}"

    properties = torch.cuda.get_device_properties(device)
    return {
        "torch_version": torch.__version__,
        "torch_hip_version": torch.version.hip,
        "device_count": device_count,
        "device_name": torch.cuda.get_device_name(device),
        "total_memory_bytes": getattr(properties, "total_memory", None),
        "device_namespace": "torch.cuda namespace backed by ROCm/HIP; not NVIDIA CUDA",
        "device": str(device),
        "synchronized_tensor_result": values,
        "synchronized": True,
    }


def main() -> int:
    try:
        result = qualify()
    except Exception as exc:  # pragma: no cover - runner-only path
        print(f"AMD_PYTORCH_PREFLIGHT: FAIL: {exc}", file=sys.stderr)
        return 1
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    print("AMD_PYTORCH_PREFLIGHT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
