from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from gpu_platform.observability_analyzer import (
    HEALTH_REPORT_FILE,
    collect_platform_metrics,
    generate_platform_health_report,
)


def main() -> None:
    metrics = collect_platform_metrics()
    report = generate_platform_health_report(metrics)
    print(f"Wrote platform health report: {HEALTH_REPORT_FILE}")
    print(f"Queue pressure level: {report['queue_pressure_level']}")


if __name__ == "__main__":
    main()
