$ErrorActionPreference = "Stop"
$BASE = $env:BASE
if (-not $BASE) { $BASE = "http://127.0.0.1:8002" }

Write-Host "BASE=$BASE"

Write-Host "`n1) Health check: /docs"
curl.exe -s "$BASE/docs" | Out-Null
Write-Host "✅ /docs reachable"

Write-Host "`n2) Eval run: /eval/run"
$stats = curl.exe -s -X POST "$BASE/eval/run" -H "accept: application/json" |
  ConvertFrom-Json | Select-Object -ExpandProperty stats

$fmt = "{0,-15} {1,-22} {2,-12} {3,-14}" -f "total_questions","questions_with_citations","hit_rate_pct","avg_latency_ms"
$val = "{0,-15} {1,-22} {2,-12:N1} {3,-14:N1}" -f $metrics.total_questions,$metrics.questions_with_citations,$metrics.hit_rate_pct,$metrics.avg_latency_ms
Write-Host $fmt
Write-Host $val

Write-Host "✅ smoke passed"
