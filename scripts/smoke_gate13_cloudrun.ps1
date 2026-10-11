param(
  [Parameter(Mandatory = $true)]
  [string]$BaseUrl,

  [Parameter(Mandatory = $true)]
  [string]$ApiKey
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd("/")

Write-Host "BASE=$base"

$health = Invoke-WebRequest -UseBasicParsing "$base/health"
if ($health.StatusCode -ne 200) {
  throw "Expected /health HTTP 200, got $($health.StatusCode)"
}
Write-Host "health_status=$($health.StatusCode)"

$unauthenticatedMetricsStatus = 0
try {
  Invoke-WebRequest -UseBasicParsing "$base/metrics" | Out-Null
} catch {
  $unauthenticatedMetricsStatus = [int]$_.Exception.Response.StatusCode
}
if ($unauthenticatedMetricsStatus -ne 401) {
  throw "Expected unauthenticated /metrics HTTP 401, got $unauthenticatedMetricsStatus"
}
Write-Host "unauthenticated_metrics_status=$unauthenticatedMetricsStatus"

$headers = @{ "X-AgentTrust-API-Key" = $ApiKey }
$metrics = Invoke-WebRequest -UseBasicParsing "$base/metrics" -Headers $headers
if ($metrics.StatusCode -ne 200) {
  throw "Expected authenticated /metrics HTTP 200, got $($metrics.StatusCode)"
}
Write-Host "authenticated_metrics_status=$($metrics.StatusCode)"

$payload = @{
  prompt = "Summarize the deployment evidence."
  model_response = "The service passed health checks. [1]"
  expected_behavior = "Answer with citation."
  risk_category = "citation"
  retrieved_evidence = @(
    @{
      source_id = "1"
      snippet = "The service passed health checks."
    }
  )
} | ConvertTo-Json -Depth 5

$evaluation = Invoke-RestMethod `
  -Method Post `
  -Uri "$base/evaluate" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $payload

if (-not $evaluation.run_id) {
  throw "Authenticated /evaluate did not return a run_id"
}
Write-Host "evaluation_run_id=$($evaluation.run_id)"
Write-Host "evaluation_pass=$($evaluation.pass)"
