from __future__ import annotations

import importlib
import platform
import uuid
from pathlib import Path


def test_platform_resolves_to_stdlib_and_uuid_initializes() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    resolved_platform = Path(platform.__file__).resolve()

    assert repository_root not in resolved_platform.parents
    assert callable(platform.system)
    assert platform.system()
    assert uuid.uuid4()

    for module_name in ("gpu_platform.api", "gpu_platform.request_router", "gpu_orchestration.api"):
        module = importlib.import_module(module_name)
        assert module.__name__ == module_name
        assert module.__spec__ is not None
        assert module.__spec__.name == module_name
