# AgentTrust GPU Reliability Lab

The GPU Reliability Lab is an evidence-first benchmark runner integrated with AgentTrust IQ. It combines request reliability metrics with the repository's separate deterministic quality/safety evaluator; provider/API failures are never scored as model-quality failures.

It supports deterministic offline mock runs, OpenAI-compatible endpoints, and the NVIDIA NIM OpenAI-compatible endpoint. Network access is disabled unless `--allow-network` is supplied. Dashboard routes are read-only and never submit provider requests.

```bash
python -m gpu_lab.runner --provider mock --mode mock-benchmark --profile moderate --suite eval/nvidia_nemotron_pack.jsonl
python -m gpu_lab.runner --provider nvidia_nim --mode authenticated-smoke --model "$NVIDIA_MODELS" --max-requests 5 --concurrency 1 --allow-network --resume
python -m gpu_lab.runner --provider openai_compatible --mode authenticated-benchmark --profile performance --model "$GPU_LAB_MODEL" --max-requests 50 --telemetry amd_smi --allow-network --confirm-performance-run --resume
```

Every run writes `run-manifest.json`, `requests.jsonl`, `benchmark-summary.json`, `quality-summary.json`, `telemetry.jsonl`, and `failure-analysis.csv` under `artifacts/gpu-lab/<run_id>/`. Mock runs are labelled **“Deterministic mock run — not a GPU benchmark.”** No-run dashboards say **“No authenticated GPU benchmark has been completed.”** Null metrics mean “Not measured.”

AMD SMI is optional: absence is reported as `telemetry_status=unavailable` and does not fail a run. Endpoint hosts are sanitized and credentials are not written to artifacts.

## Reproducible screenshot capture

Run the offline mock command above, start the API with the repository's normal server command, then open `/gpu-lab` and capture it as `screenshots/gpu-lab-mock-run.png`. Before any run, capture `/gpu-lab` as `screenshots/gpu-lab-not-run.png`. Do not capture or label an authenticated-result screenshot until an authenticated benchmark has completed.
