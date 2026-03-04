import json
import os
import time
import requests

SERVICE_URL = os.environ.get("SERVICE_URL", "http://127.0.0.1:8000")

def main():
    t0 = time.time()

    # Basic smoke checks: health + stats
    health = requests.get(f"{SERVICE_URL}/health", timeout=10)
    stats = requests.get(f"{SERVICE_URL}/stats", timeout=10)

    ok = (health.status_code == 200) and (stats.status_code == 200)

    metrics = {
        "ok": ok,
        "health_status": health.status_code,
        "stats_status": stats.status_code,
        "latency_ms_total": round((time.time() - t0) * 1000, 2),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    os.makedirs("runs", exist_ok=True)
    with open("runs/ci_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    # Gate: fail if not ok
    if not ok:
        raise SystemExit("CI GATE FAIL: service endpoints not healthy")

if __name__ == "__main__":
    main()
