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

$stats | Format-Table

Write-Host "✅ smoke passed"
