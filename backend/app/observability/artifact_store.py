from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .models import InferenceEvent

DEFAULT_ROOT = Path("artifacts") / "inference_events"


class InferenceArtifactStore:
    def __init__(self, root_dir: Path | None = None):
        configured_root = os.getenv("INFERENCE_ARTIFACTS_ROOT", "").strip()
        if root_dir is not None:
            self._root_dir = root_dir
        elif configured_root:
            self._root_dir = Path(configured_root)
        else:
            self._root_dir = DEFAULT_ROOT

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    def persist_event(self, event: InferenceEvent) -> Path:
        now = datetime.now(timezone.utc)
        partition = self._root_dir / f"year={now.year}" / f"month={now.month:02d}" / f"day={now.day:02d}"
        partition.mkdir(parents=True, exist_ok=True)

        out_path = partition / "inference_events.jsonl"
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
        return out_path
