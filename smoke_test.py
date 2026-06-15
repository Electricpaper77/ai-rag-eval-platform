import requests

URL = "https://ai-agent-reliability-platform-rtcd.vercel.app/agenttrust-iq-command-center.html"
EXPECTED_MARKERS = ("AgentTrust IQ", "Agent Readiness Score")


def run_smoke_test() -> None:
    response = requests.get(URL, timeout=10)
    response.raise_for_status()
    missing = [marker for marker in EXPECTED_MARKERS if marker not in response.text]
    if missing:
        raise RuntimeError(f"Command Center is missing expected content: {', '.join(missing)}")


def test_smoke_configuration() -> None:
    assert URL.startswith("https://")
    assert URL.endswith("/agenttrust-iq-command-center.html")


if __name__ == "__main__":
    run_smoke_test()
    print("Smoke test passed")
