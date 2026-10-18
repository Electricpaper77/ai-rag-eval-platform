"""Optional real AMD hardware probe.

CPU-only CI intentionally exits successfully with ``AMD_HARDWARE:
NOT_EXECUTED``.  A PASS is emitted only after runtime evidence and a small
vector computation both succeed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.gpu_runtime import detect_rocm_runtime


def _torch_vector_add() -> dict[str, object]:
    try:
        import torch  # type: ignore
    except Exception as exc:
        return {"ok": False, "reason": f"torch unavailable: {exc}"}
    if not getattr(torch, "version", None) or not getattr(torch.version, "hip", None):
        return {"ok": False, "reason": "PyTorch HIP runtime unavailable"}
    if not torch.cuda.is_available():
        return {"ok": False, "reason": "PyTorch reports no HIP device"}
    try:
        left = torch.tensor([1.0, 2.0, 3.0], device="cuda")
        right = torch.tensor([4.0, 5.0, 6.0], device="cuda")
        result = (left + right).cpu().tolist()
        return {"ok": result == [5.0, 7.0, 9.0], "result": result}
    except Exception as exc:  # pragma: no cover - hardware-only path
        return {"ok": False, "reason": str(exc)}


def main() -> int:
    status = detect_rocm_runtime()
    computation: dict[str, object] = {"ok": False, "reason": "no AMD device detected"}
    if status["vendor"] == "AMD" and status["device_count"] > 0:
        computation = _torch_vector_add()
    result = {"runtime": status, "computation": computation}
    print(json.dumps(result, sort_keys=True))
    if status["vendor"] != "AMD" or status["device_count"] == 0:
        print("AMD_HARDWARE: NOT_EXECUTED")
        return 0
    if computation.get("ok") is True:
        print("AMD_HARDWARE: PASS")
        return 0
    print("AMD_HARDWARE: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
