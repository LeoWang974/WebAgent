$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "services\api"
$python = Join-Path $apiRoot ".venv\Scripts\python.exe"
$secretDirectory = Join-Path $repoRoot "runtime\secrets"
$secretFile = Join-Path $secretDirectory "model-config.key"

Set-Location $apiRoot

$workerConcurrency = if ($env:WORKER_CONCURRENCY) { $env:WORKER_CONCURRENCY } else { "2" }
$workerQueues = if ($env:WORKER_QUEUES) { $env:WORKER_QUEUES } else { "short-chat,agent-runs" }
$workerPool = if ($env:WORKER_POOL) { $env:WORKER_POOL } else { "solo" }

if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend venv not found: $python"
}

if (-not $env:MODEL_CONFIG_ENCRYPTION_KEY) {
  New-Item -ItemType Directory -Force -Path $secretDirectory | Out-Null
  if (-not (Test-Path -LiteralPath $secretFile)) {
    $generatedKey = & $python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode('ascii'))"
    if ($LASTEXITCODE -ne 0 -or -not $generatedKey) {
      throw "Unable to generate the model credential encryption key."
    }
    Set-Content -LiteralPath $secretFile -Value $generatedKey.Trim() -Encoding ascii -NoNewline
  }
  $env:MODEL_CONFIG_ENCRYPTION_KEY = (Get-Content -LiteralPath $secretFile -Raw).Trim()
}

& $python -m celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=$workerConcurrency --queues=$workerQueues --pool=$workerPool
