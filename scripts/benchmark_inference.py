import requests
import time
import statistics
import json
import os

URL = "http://34.121.205.47/query"
REQUESTS = 30

latencies = []
errors = 0

for i in range(REQUESTS):
    start = time.time()

    try:
        r = requests.post(
            URL,
            json={"query": "What is Kubernetes?"}
        )

        latency = (time.time() - start) * 1000
        latencies.append(latency)

        if r.status_code != 200:
            errors += 1

    except Exception:
        errors += 1

results = {
    "requests_sent": REQUESTS,
    "p50_latency_ms": round(statistics.median(latencies),2),
    "p95_latency_ms": round(sorted(latencies)[int(len(latencies)*0.95)],2),
    "avg_latency_ms": round(statistics.mean(latencies),2),
    "error_rate": round(errors / REQUESTS,3),
    "requests_per_second": round(REQUESTS / sum(latencies) * 1000,2)
}

os.makedirs("docs/artifacts", exist_ok=True)

with open("docs/artifacts/inference_benchmark.json","w") as f:
    json.dump(results,f,indent=2)

print("Benchmark complete")
print(results)
