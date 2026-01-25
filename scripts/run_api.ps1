param(
  [int]$Port = 8002,
  [string]$Host = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

Push-Location (Join-Path $PSScriptRoot "..\backend")
python -m uvicorn app.main:app --host $Host --port $Port
Pop-Location
