from __future__ import annotations

from gpu_platform.concurrency_controller import decide_scale_action, estimate_queue_latency


def test_estimate_queue_latency_when_under_capacity() -> None:
    assert estimate_queue_latency(active_jobs=5) == 0.0


def test_estimate_queue_latency_when_over_capacity() -> None:
    assert estimate_queue_latency(active_jobs=12) == 3.0


def test_decide_scale_action() -> None:
    assert decide_scale_action(queue_size=7) == "scale_up"
    assert decide_scale_action(queue_size=1) == "scale_down"
    assert decide_scale_action(queue_size=3) == "hold"
