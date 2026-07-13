$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "services\api"
$envFile = Join-Path $apiRoot ".env"
$envExample = Join-Path $apiRoot ".env.example"

if (-not (Test-Path -LiteralPath $envFile) -and (Test-Path -LiteralPath $envExample)) {
  Copy-Item -LiteralPath $envExample -Destination $envFile
}

Set-Location -LiteralPath $apiRoot
$env:PYTHONUNBUFFERED = "1"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --log-level info
