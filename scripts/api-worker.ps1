$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "services\api"

Set-Location $apiRoot

$workerConcurrency = if ($env:WORKER_CONCURRENCY) { $env:WORKER_CONCURRENCY } else { "2" }

celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=$workerConcurrency
