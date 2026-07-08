$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "services\api"

Set-Location $apiRoot

celery -A app.workers.celery_app.celery_app worker --loglevel=info

