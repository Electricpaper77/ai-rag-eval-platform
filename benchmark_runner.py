import json
import time
import statistics
import argparse
import requests

parser = argparse.ArgumentParser()
parser.add_argument("--dataset", required=True)
parser.add_argument("--batch-size", type=int, default=100)
parser.add_argument("--endpoint", default="http://localhost:8000/evaluate")
args = parser.parse_args()

latencies = []
passes = 0
total = 0

with open(args.dataset) as f:
    prompts = [json.loads(line) for line in f]

start_time = time.time()

for item in prompts[:args.batch_size]:
    prompt = item.get("prompt", "")
    t0 = time.time()

    try:
        r = requests.post(args.endpoint, json={"prompt": prompt})
        latency = (time.time() - t0) * 1000
        latencies.append(latency)

        result = r.json()
        if result.get("pass", False):
            passes += 1

        total += 1

    except Exception:
        total += 1

end_time = time.time()

p50 = statistics.median(latencies)
p95 = statistics.quantiles(latencies, n=100)[94]
throughput = total / (end_time - start_time)

summary = {
    "prompts": total,
    "pass_rate": passes / total if total else 0,
    "p50_latency_ms": round(p50,2),
    "p95_latency_ms": round(p95,2),
    "throughput_rps": round(throughput,2)
}

print(json.dumps(summary, indent=2))

timestamp = int(time.time())
with open(f"benchmark_{timestamp}.json", "w") as f:
    json.dump(summary, f, indent=2)
