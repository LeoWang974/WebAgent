$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "services\api"

Set-Location $apiRoot

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

uvicorn app.main:app --reload --port 8000

