$latest = Get-ChildItem .\runs\eval_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $latest) { throw "No eval_*.json found in .\runs" }

$obj = Get-Content $latest.FullName -Raw | ConvertFrom-Json

$total = [int]$obj.stats.total_questions
$withCite = [int]$obj.stats.questions_with_citations
$rate = if ($total -gt 0) { [math]::Round(100 * $withCite / $total, 1) } else { 0 }

$avg = [double]$obj.stats.avg_latency_ms

$latencies = @()
foreach ($r in $obj.results) { $latencies += [double]$r.latency_ms }
$latencies = $latencies | Sort-Object

function Percentile($arr, $p) {
  if (-not $arr -or $arr.Count -eq 0) { return $null }
  $n = $arr.Count
  $idx = [math]::Ceiling($p * $n) - 1
  if ($idx -lt 0) { $idx = 0 }
  if ($idx -ge $n) { $idx = $n - 1 }
  return $arr[$idx]
}

$p50 = Percentile $latencies 0.50
$p95 = Percentile $latencies 0.95
$p99 = Percentile $latencies 0.99

Write-Host ""
Write-Host "Latest eval:" $latest.Name
Write-Host "Total questions:" $total
Write-Host "With citations:" $withCite
Write-Host "Citation rate:" ("{0}%" -f $rate)
Write-Host "Avg latency (ms):" $avg
Write-Host "P50 latency (ms):" $p50
Write-Host "P95 latency (ms):" $p95
Write-Host "P99 latency (ms):" $p99
Write-Host ""
