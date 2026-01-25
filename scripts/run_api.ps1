param(
  [int]$Port = 8002,
  [string]$BindHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

# Always resolve relative to THIS script's folder (works when executed via -File)
$repoRoot  = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $repoRoot "backend"

if (-not (Test-Path $backendDir)) {
  throw "backend folder not found at: $backendDir"
}

Push-Location $backendDir
python -m uvicorn app.main:app --host $BindHost --port $Port
Pop-Location
