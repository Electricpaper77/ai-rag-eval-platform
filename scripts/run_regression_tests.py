import json
import requests

DATASET="eval/regression_dataset.jsonl"
ENDPOINT="http://localhost:8000/evaluate"

passes=0
total=0

with open(DATASET) as f:
    for line in f:
        item=json.loads(line)
        prompt=item["prompt"]
        expected=item["expected"]

        r=requests.post(ENDPOINT,json={"prompt":prompt})
        answer=r.json().get("answer","")

        if expected.lower() in answer.lower():
            passes+=1

        total+=1

pass_rate=passes/total if total else 0

print({
    "tests": total,
    "passes": passes,
    "pass_rate": pass_rate
})
