param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [int]$Concurrency = 10,
  [int]$Requests = 200
)

$ErrorActionPreference = "Stop"
$endpoint = "/query"
$url = ($BaseUrl.TrimEnd("/") + $endpoint)

$body = @{ question = "load test" } | ConvertTo-Json -Compress
$headers = @{ "Content-Type" = "application/json" }

# Ensure runs dir exists
if (!(Test-Path ".\runs")) { New-Item -ItemType Directory -Path ".\runs" | Out-Null }

$swTotal = [System.Diagnostics.Stopwatch]::StartNew()

# Create runspaces (thread pool)
$pool = [runspacefactory]::CreateRunspacePool(1, $Concurrency)
$pool.Open()

$tasks = New-Object System.Collections.Generic.List[object]

for ($i=1; $i -le $Requests; $i++) {
  $ps = [powershell]::Create()
  $ps.RunspacePool = $pool

  [void]$ps.AddScript({
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

    [pscustomobject]@{ ok = $ok; latency_ms = [double]$sw.Elapsed.TotalMilliseconds }
  }).AddArgument($url).AddArgument($body).AddArgument($headers)

  $handle = $ps.BeginInvoke()
  $tasks.Add([pscustomobject]@{ ps=$ps; handle=$handle })
}

$results = @()
foreach ($t in $tasks) {
  $results += $t.ps.EndInvoke($t.handle)
  $t.ps.Dispose()
}

$pool.Close()
$pool.Dispose()

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
