import json
import statistics

file = "docs/artifacts/runs/eval_run_001.jsonl"

latencies = []
passes = 0
total = 0

with open(file) as f:
    for line in f:
        r = json.loads(line)
        total += 1

        if r.get("latency_ms") is not None:
            latencies.append(r["latency_ms"])

        if r.get("eval_pass"):
            passes += 1

summary = {
    "total_prompts": total,
    "avg_latency_ms": int(statistics.mean(latencies)),
    "p95_latency_ms": int(sorted(latencies)[int(len(latencies)*0.95)]),
    "eval_pass_rate": round(passes / total, 3)
}

import os
os.makedirs("docs/artifacts/reports", exist_ok=True)

with open("docs/artifacts/reports/eval_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print("Summary generated: docs/artifacts/reports/eval_summary.json")
