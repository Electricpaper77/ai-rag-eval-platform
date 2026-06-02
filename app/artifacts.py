from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactWriter:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def append_jsonl(self, filename: str, payload: dict[str, Any]) -> None:
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def write_text(self, filename: str, content: str) -> None:
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
