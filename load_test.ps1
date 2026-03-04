param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [int]$Concurrency = 10,
  [int]$Requests = 200
)

$ErrorActionPreference = "Stop"
$endpoint = "/query"
$url = ($BaseUrl.TrimEnd("/") + $endpoint)

$body = @{ query = "load test" } | ConvertTo-Json -Compress
$headers = @{ "Content-Type" = "application/json" }

$swTotal = [System.Diagnostics.Stopwatch]::StartNew()

# Run N requests in parallel with throttling = concurrency
$results = 1..$Requests | ForEach-Object -Parallel {
  param($url,$body,$headers)

  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $ok = $true
  try {
    $resp = Invoke-WebRequest -Uri $url -Method POST -Headers $headers -Body $body -TimeoutSec 60
    if ($resp.StatusCode -lt 200 -or $resp.StatusCode -ge 300) { $ok = $false }
  } catch {
    $ok = $false
  } finally {
    $sw.Stop()
  }

  [pscustomobject]@{
    ok = $ok
    latency_ms = [double]$sw.Elapsed.TotalMilliseconds
  }

} -ThrottleLimit $Concurrency -ArgumentList $url,$body,$headers

$swTotal.Stop()

$lat = $results.latency_ms | Sort-Object
$total = $lat.Count
if ($total -eq 0) { throw "No latency samples collected." }

$idx = [math]::Ceiling(0.95 * $total) - 1
if ($idx -lt 0) { $idx = 0 }
$p95 = [math]::Round($lat[$idx], 2)

$errCount = ($results | Where-Object { -not $_.ok }).Count
$errRate = [math]::Round(($errCount / $Requests) * 100, 2)
$rps = [math]::Round(($Requests / $swTotal.Elapsed.TotalSeconds), 2)

Write-Output "URL: $url"
Write-Output "CONCURRENCY: $Concurrency"
Write-Output "REQUESTS: $Requests"
Write-Output "RPS: $rps"
Write-Output "P95_MS: $p95"
Write-Output "ERRORS: $errCount"
Write-Output "ERROR_RATE_PCT: $errRate"
