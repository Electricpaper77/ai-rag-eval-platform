import requests

URL = "https://llm-inference-api-69725201265.us-central1.run.app/health"


def run_smoke_test() -> None:
    response = requests.get(URL, timeout=10)
    if response.status_code != 200:
        raise Exception("Health check failed")


def test_smoke_configuration() -> None:
    assert URL.startswith("https://")


if __name__ == "__main__":
    run_smoke_test()
    print("Smoke test passed")
