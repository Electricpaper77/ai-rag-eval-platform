import requests

URL = "https://llm-inference-api-69725201265.us-central1.run.app/health"

r = requests.get(URL, timeout=10)

if r.status_code != 200:
    raise Exception("Health check failed")

print("Smoke test passed")
