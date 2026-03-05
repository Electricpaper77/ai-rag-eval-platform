
## Performance Validation

Load testing was performed using k6 against the deployed Cloud Run service.

Service:
https://ai-rag-eval-69725201265.us-central1.run.app

### Baseline Test (10 VUs)

avg latency: ~47 ms  
p95 latency: ~52 ms  
throughput: ~9 req/sec  

Artifact:
docs/artifacts/load_test_results.json

### Scaling Test (25 VUs)

throughput: ~23 req/sec  
p95 latency: ~1.05 s  

Artifact:
docs/artifacts/load_test_25vus.json

### Stress Test (50 VUs)

throughput: ~43 req/sec  
p95 latency: ~1.05 s  
success rate: ~99%

Artifact:
docs/artifacts/load_test_50vus.json


## System Architecture

```mermaid
flowchart TD
  U[User / Client] -->|HTTP| CR[Cloud Run: FastAPI Service]
  CR --> H[/health]
  CR --> D[/docs]
  CR --> M[/metrics (Prometheus)]
  CR --> E[Evaluation Harness (Regression Suite)]
  E --> A[Artifacts: JSONL runs + docs/artifacts/*]
  CR --> R[Retriever / Vector DB (ChromaDB / Pinecone)]
  R --> CR
  CR --> L[LLM Inference (model endpoint)]
  L --> CR

