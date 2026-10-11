param(
  [Parameter(Mandatory = $true)]
  [string]$BaseUrl,

  [Parameter(Mandatory = $true)]
  [string]$ApiKey,

  [string]$IdentityToken = $env:CLOUD_RUN_IDENTITY_TOKEN
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd("/")

function Get-StatusCode {
  param(
    [Parameter(Mandatory = $true)]
    [scriptblock]$Request
  )

  try {
    $response = & $Request
    return [int]$response.StatusCode
  } catch {
    if ($_.Exception.Response) {
      return [int]$_.Exception.Response.StatusCode
    }
    throw
  }
}

function Assert-StatusCode {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [Parameter(Mandatory = $true)]
    [int]$Expected,

    [Parameter(Mandatory = $true)]
    [scriptblock]$Request
  )

  $actual = Get-StatusCode -Request $Request
  if ($actual -ne $Expected) {
    throw "Expected $Name HTTP $Expected, got $actual"
  }
  Write-Host "$($Name)_status=$actual"
}

if (-not $IdentityToken) {
  throw "Cloud Run IAM identity token is required. Set CLOUD_RUN_IDENTITY_TOKEN or pass -IdentityToken. Do not print the token."
}

$iamHeaders = @{ "Authorization" = "Bearer $IdentityToken" }
$validHeaders = @{
  "Authorization" = "Bearer $IdentityToken"
  "X-AgentTrust-API-Key" = $ApiKey
}
$invalidHeaders = @{
  "Authorization" = "Bearer $IdentityToken"
  "X-AgentTrust-API-Key" = "invalid-api-key"
}

Write-Host "BASE=$base"

Assert-StatusCode -Name "iam_health" -Expected 200 -Request {
  Invoke-WebRequest -UseBasicParsing "$base/health" -Headers $iamHeaders
}

$unauthenticatedHealthStatus = Get-StatusCode -Request {
  Invoke-WebRequest -UseBasicParsing "$base/health"
}
if ($unauthenticatedHealthStatus -ne 403) {
  throw "Expected unauthenticated Cloud Run /health HTTP 403, got $unauthenticatedHealthStatus"
}
Write-Host "unauthenticated_cloud_run_health_status=403"

Assert-StatusCode -Name "unauthenticated_cloud_run_options_preflight" -Expected 403 -Request {
  Invoke-WebRequest -UseBasicParsing "$base/evaluate" -Method Options
}

Assert-StatusCode -Name "iam_authorized_missing_api_key_metrics" -Expected 401 -Request {
  Invoke-WebRequest -UseBasicParsing "$base/metrics" -Headers $iamHeaders
}

Assert-StatusCode -Name "iam_authorized_invalid_api_key_metrics" -Expected 401 -Request {
  Invoke-WebRequest -UseBasicParsing "$base/metrics" -Headers $invalidHeaders
}

Assert-StatusCode -Name "iam_authorized_valid_api_key_metrics" -Expected 200 -Request {
  Invoke-WebRequest -UseBasicParsing "$base/metrics" -Headers $validHeaders
}

$iamOptionsStatus = Get-StatusCode -Request {
  Invoke-WebRequest -UseBasicParsing "$base/evaluate" -Method Options -Headers $iamHeaders
}
if ($iamOptionsStatus -eq 401) {
  throw "IAM-authorized OPTIONS was blocked by application API-key auth; expected CORS policy handling instead"
}
Write-Host "iam_authorized_options_preflight_status=$iamOptionsStatus"

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
  -Headers $validHeaders `
  -ContentType "application/json" `
  -Body $payload

if (-not $evaluation.run_id) {
  throw "Authenticated /evaluate did not return a run_id"
}
Write-Host "evaluation_run_id=$($evaluation.run_id)"
Write-Host "evaluation_pass=$($evaluation.pass)"
