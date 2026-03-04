param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [int]$Concurrency = 10,
  [int]$Requests = 200
)

$ErrorActionPreference = "Stop"
$endpoint = "/query"
$url = ($BaseUrl.TrimEnd("/") + $endpoint)

# Basic request body (adjust if your API requires different schema)
$body = @{ query = "load test" } | ConvertTo-Json -Compress
$headers = @{ "Content-Type" = "application/json" }

$latencies = New-Object System.Collections.Concurrent.ConcurrentBag[double]
$errors = New-Object System.Collections.Concurrent.ConcurrentBag[string]

$swTotal = [System.Diagnostics.Stopwatch]::StartNew()

# Simple worker: each worker loops until global counter reaches Requests
$counter = [System.Threading.Interlocked]::Read([ref]0) # placeholder
$global:i = 0

$scriptBlock = {
  param($url,$body,$headers,$latencies,$errors,[ref]$globalI,$Requests)

  while ($true) {
    $n = [System.Threading.Interlocked]::Increment($globalI.Value)
    if ($n -gt $Requests) { break }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
      $resp = Invoke-WebRequest -Uri $url -Method POST -Headers $headers -Body $body -TimeoutSec 60
      if ($resp.StatusCode -lt 200 -or $resp.StatusCode -ge 300) {
        $errors.Add("HTTP $($resp.StatusCode)")
      }
    } catch {
      $errors.Add($_.Exception.Message)
    } finally {
      $sw.Stop()
      $latencies.Add([double]$sw.Elapsed.TotalMilliseconds)
    }
  }
}

$jobs = @()
$globalRef = [ref]$global:i

for ($k=1; $k -le $Concurrency; $k++) {
  $jobs += Start-Job -ScriptBlock $scriptBlock -ArgumentList $url,$body,$headers,$latencies,$errors,$globalRef,$Requests
}

$jobs | Wait-Job | Out-Null
$jobs | Receive-Job | Out-Null
$jobs | Remove-Job | Out-Null

$swTotal.Stop()

# Metrics
$lat = $latencies.ToArray() | Sort-Object
$total = $lat.Count
if ($total -eq 0) { throw "No latency samples collected." }

# p95 index (0-based)
$idx = [math]::Ceiling(0.95 * $total) - 1
if ($idx -lt 0) { $idx = 0 }
$p95 = [math]::Round($lat[$idx], 2)

$errCount = $errors.Count
$errRate = [math]::Round(($errCount / $Requests) * 100, 2)

$rps = [math]::Round(($Requests / $swTotal.Elapsed.TotalSeconds), 2)

Write-Host "URL: $url"
Write-Host "CONCURRENCY: $Concurrency"
Write-Host "REQUESTS: $Requests"
Write-Host "RPS: $rps"
Write-Host "P95_MS: $p95"
Write-Host "ERRORS: $errCount"
Write-Host "ERROR_RATE_PCT: $errRate"
