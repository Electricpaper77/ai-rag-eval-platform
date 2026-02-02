param(
  [string]$BaseUrl = ""
)

if (-not $BaseUrl) {
  $BaseUrl = (gcloud run services describe rag-eval-api --region us-central1 --format="value(status.url)")
}

Write-Host "BASE=$BaseUrl"

# Health
Invoke-RestMethod "$BaseUrl/health" | Format-Table

# Ingest from GCS (adjust bucket/path if needed)
$body = @{ path="gs://rag-eval-docs-124909/sample_docs" } | ConvertTo-Json
Invoke-RestMethod -Method POST -Uri "$BaseUrl/ingest" -ContentType "application/json" -Body $body -TimeoutSec 180 | Format-List

# Query (default top_k = 3)
$q = @{ question="Summarize the refund policy with citations." } | ConvertTo-Json
$r = Invoke-RestMethod -Method POST -Uri "$BaseUrl/query" -ContentType "application/json" -Body $q -TimeoutSec 60

$r.status
$r.num_citations
$r.citations.source
$r.latency_ms
