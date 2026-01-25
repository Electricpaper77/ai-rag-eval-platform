param(
  [string]$Base = $env:BASE
)

if ([string]::IsNullOrWhiteSpace($Base)) {
  $Base = "http://127.0.0.1:8002"
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$outPath = ".\runs\eval_$ts.json"

Write-Host "BASE=$Base"
Write-Host "Saving to $outPath"

# Call eval endpoint and save raw JSON
$response = curl.exe -s -X POST "$Base/eval/run" -H "accept: application/json"
if ([string]::IsNullOrWhiteSpace($response)) {
  Write-Error "Empty response from $Base/eval/run"
  exit 1
}

$response | Out-File -Encoding utf8 $outPath

# Parse + print summary if possible
try {
  $obj = $response | ConvertFrom-Json
  $total = $obj.total_questions
  $withCites = $obj.questions_with_citations
  $hit = $obj.hit_rate_pct
  $lat = $obj.avg_latency_ms
  Write-Host ""
  Write-Host "total_questions=$total  questions_with_citations=$withCites  hit_rate_pct=$hit  avg_latency_ms=$lat"
  Write-Host "✅ report saved"
} catch {
  Write-Warning "Saved raw JSON, but could not parse summary fields. Check $outPath"
}
