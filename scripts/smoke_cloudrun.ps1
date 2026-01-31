$BASE="https://rag-eval-api-69725201265.us-central1.run.app"
Write-Host "BASE=$BASE"

# docs
irm "$BASE/docs" -TimeoutSec 60 | Out-Null
Write-Host "✅ /docs OK"

# openapi
$o = irm "$BASE/openapi.json" -TimeoutSec 60
Write-Host ("✅ openapi: " + $o.info.title + " v" + $o.info.version)

# optional health
foreach($p in @("/health","/healthz")) {
  try { irm ("$BASE" + $p) -TimeoutSec 30 | Out-Null; Write-Host ("✅ " + $p + " OK") } catch { Write-Host ("(skip) " + $p) }
}
