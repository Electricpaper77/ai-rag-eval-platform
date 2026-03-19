# LLM Evaluation Results + Leaderboard

## Overview
Evaluation platform comparing LLM performance across quality, latency, and cost using 120+ prompts.

---

## Leaderboard

| Model        | Pass Rate | Hallucination Rate | Latency (p95) | Cost / Request |
|-------------|----------|--------------------|--------------|----------------|
| GPT-4o      | 87%      | 6%                 | 270ms        | $0.009         |
| GPT-3.5     | 78%      | 12%                | 180ms        | $0.004         |
| Claude      | 82%      | 8%                 | 240ms        | $0.007         |

---

## Key Metrics

- Prompts evaluated: 120+  
- Evaluation runs: 1,000+  
- Throughput: ~43 req/sec  
- Success rate: 99%  

---

## Evaluation Metrics

- **Hallucination Rate**: % of responses with incorrect or unsupported claims  
- **Pass Rate**: % of responses meeting validation criteria  
- **Citation Precision**: Accuracy of retrieved references  
- **Refusal Accuracy**: Correct rejection of unsafe/invalid prompts  

---

## Sample Output (JSONL)

```json
{"prompt": "What is X?", "response": "...", "pass": true, "hallucination": false, "latency_ms": 120}

## Screenshot

![Evaluation Results](screenshots/eval_results.png)


## Before vs After Improvements

| Metric               | Before | After |
|---------------------|--------|-------|
| Hallucination Rate  | 18%    | 6%    |
| Pass Rate           | 72%    | 87%   |
| Latency (p95)       | ~320ms | ~270ms |

### What Changed
- Added structured evaluation metrics (hallucination, citation precision, refusal accuracy)
- Implemented regression testing and CI gating
- Optimized retrieval pipeline and model selection

