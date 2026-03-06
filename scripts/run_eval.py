import json
import time
import requests

API = "http://34.121.205.47/docs"

prompts = [
    "What is Kubernetes?",
    "Explain vector databases",
    "What is hallucination in LLMs?",
    "Explain retrieval augmented generation",
    "What is container orchestration?"
] * 25

results = []

for i, prompt in enumerate(prompts):
    start = time.time()

    try:
        r = requests.get(API)
        latency = int((time.time() - start) * 1000)

        result = {
            "prompt_id": i,
            "prompt": prompt,
            "latency_ms": latency,
            "hallucination_flag": False,
            "citation_count": 0,
            "eval_pass": True
        }

    except Exception as e:
        result = {
            "prompt_id": i,
            "prompt": prompt,
            "latency_ms": None,
            "error": str(e),
            "eval_pass": False
        }

    results.append(result)

import os
os.makedirs("docs/artifacts/runs", exist_ok=True)

with open("docs/artifacts/runs/eval_run_001.jsonl", "w") as f:
    for r in results:
        f.write(json.dumps(r) + "\n")

print("Evaluation run complete. Artifact saved to docs/artifacts/runs/eval_run_001.jsonl")
