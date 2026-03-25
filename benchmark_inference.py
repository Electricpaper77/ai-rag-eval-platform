import requests
import time

URL = "http://localhost:8000/v1/chat/completions"

payload = {
    "query": "benchmark test"
}

N = 50

start = time.time()

for _ in range(N):
    requests.post(URL, json=payload)

total = time.time() - start

print("requests:", N)
print("total_time:", total)
print("req_per_sec:", N/total)
print("avg_latency:", total/N)

