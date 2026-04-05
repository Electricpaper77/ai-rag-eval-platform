from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from gpu_platform.shadow_eval import write_shadow_summary


def main() -> None:
    summary = write_shadow_summary()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
