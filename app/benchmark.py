from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RequestRecord:
    backend: str
    policy: str
    latency_seconds: float
    time_to_first_token_seconds: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    success: bool
    created_at: float


class BenchmarkRecorder:
    def __init__(self) -> None:
        self.records: list[RequestRecord] = []

    def record(self, record: RequestRecord) -> None:
        self.records.append(record)

    def backend_latency(self, backend: str, default_ms: float) -> float:
        latencies = [r.latency_seconds * 1000 for r in self.records if r.backend == backend and r.success]
        if not latencies:
            return default_ms
        return percentile(latencies, 50)

    def summary(self) -> dict:
        if not self.records:
            return {
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "requests_per_second": 0,
                "tokens_per_second": 0,
                "time_to_first_token_ms": 0,
                "error_rate": 0,
                "cost_per_request_usd": 0,
                "total_requests": 0,
                "leaderboard": [],
                "by_backend": {},
            }
        latencies = [r.latency_seconds * 1000 for r in self.records]
        successes = [r for r in self.records if r.success]
        total_tokens = sum(r.total_tokens for r in successes)
        total_latency = sum(r.latency_seconds for r in successes) or 1e-9
        elapsed = max(1e-9, max(r.created_at for r in self.records) - min(r.created_at for r in self.records))
        return {
            "p50_latency_ms": round(percentile(latencies, 50), 2),
            "p95_latency_ms": round(percentile(latencies, 95), 2),
            "requests_per_second": round(len(self.records) / elapsed, 2),
            "tokens_per_second": round(total_tokens / total_latency, 2),
            "time_to_first_token_ms": round(percentile([r.time_to_first_token_seconds * 1000 for r in successes], 50), 2)
            if successes
            else 0,
            "error_rate": round((len(self.records) - len(successes)) / len(self.records), 4),
            "cost_per_request_usd": round(sum(r.cost_usd for r in successes) / len(successes), 8) if successes else 0,
            "total_requests": len(self.records),
            "leaderboard": self.leaderboard(),
            "by_backend": self._by_backend(),
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.summary(), indent=2) + "\n", encoding="utf-8")

    def write_leaderboard(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.leaderboard()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "rank",
                    "backend",
                    "requests",
                    "p50_latency_ms",
                    "p95_latency_ms",
                    "ttft_p50_ms",
                    "tokens_per_second",
                    "error_rate",
                    "cost_per_request_usd",
                    "score",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    def leaderboard(self) -> list[dict]:
        rows = []
        for backend in sorted({r.backend for r in self.records}):
            records = [r for r in self.records if r.backend == backend]
            successes = [r for r in records if r.success]
            total_latency = sum(r.latency_seconds for r in successes) or 1e-9
            tokens_per_second = sum(r.total_tokens for r in successes) / total_latency
            error_rate = (len(records) - len(successes)) / len(records)
            cost_per_request = sum(r.cost_usd for r in successes) / len(successes) if successes else 0
            p95_latency = percentile([r.latency_seconds * 1000 for r in records], 95)
            ttft_p50 = percentile([r.time_to_first_token_seconds * 1000 for r in successes], 50) if successes else 0
            score = (tokens_per_second / max(p95_latency, 1)) * (1 - error_rate) / max(cost_per_request, 1e-9)
            rows.append(
                {
                    "backend": backend,
                    "requests": len(records),
                    "p50_latency_ms": round(percentile([r.latency_seconds * 1000 for r in records], 50), 2),
                    "p95_latency_ms": round(p95_latency, 2),
                    "ttft_p50_ms": round(ttft_p50, 2),
                    "tokens_per_second": round(tokens_per_second, 2),
                    "error_rate": round(error_rate, 4),
                    "cost_per_request_usd": round(cost_per_request, 8),
                    "score": round(score, 2),
                }
            )
        ranked = sorted(rows, key=lambda row: row["score"], reverse=True)
        for index, row in enumerate(ranked, start=1):
            row["rank"] = index
        return ranked

    def _by_backend(self) -> dict[str, dict]:
        backends = sorted({r.backend for r in self.records})
        data = {}
        for backend in backends:
            records = [r for r in self.records if r.backend == backend]
            successes = [r for r in records if r.success]
            data[backend] = {
                "requests": len(records),
                "error_rate": round((len(records) - len(successes)) / len(records), 4),
                "p50_latency_ms": round(percentile([r.latency_seconds * 1000 for r in records], 50), 2),
                "p95_latency_ms": round(percentile([r.latency_seconds * 1000 for r in records], 95), 2),
                "ttft_p50_ms": round(
                    percentile([r.time_to_first_token_seconds * 1000 for r in successes], 50), 2
                )
                if successes
                else 0,
                "tokens_per_second": round(
                    sum(r.total_tokens for r in successes) / (sum(r.latency_seconds for r in successes) or 1e-9),
                    2,
                ),
                "tokens_generated": sum(r.completion_tokens for r in successes),
            }
        return data


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def sample_record(backend: str, policy: str, latency_ms: float, tokens: int, cost: float) -> RequestRecord:
    return RequestRecord(
        backend=backend,
        policy=policy,
        latency_seconds=latency_ms / 1000,
        time_to_first_token_seconds=min(latency_ms / 1000, 0.025),
        prompt_tokens=max(1, tokens // 3),
        completion_tokens=max(1, tokens - max(1, tokens // 3)),
        total_tokens=tokens,
        cost_usd=cost,
        success=True,
        created_at=time.time(),
    )
