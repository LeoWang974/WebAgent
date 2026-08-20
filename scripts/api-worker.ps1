# File purpose: Automates the api worker development, deployment, or maintenance workflow.
# Main declarations: this file contains declarative configuration or re-exports and has no
# callable declarations.

param(
  [string]$Queues = "",
  [string]$WorkerName = "",
  [int]$Concurrency = 0,
  [string]$Pool = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "services\api"
$python = Join-Path $apiRoot ".venv\Scripts\python.exe"
$secretDirectory = Join-Path $repoRoot "runtime\secrets"
$secretFile = Join-Path $secretDirectory "model-config.key"

Set-Location $apiRoot

$workerConcurrency = if ($Concurrency -gt 0) {
  "$Concurrency"
} elseif ($env:WORKER_CONCURRENCY) {
  $env:WORKER_CONCURRENCY
} else {
  "1"
}
$workerQueues = if ($Queues) {
  $Queues
} elseif ($env:WORKER_QUEUES) {
  $env:WORKER_QUEUES
} else {
  "short-chat,agent-runs"
}
$workerPool = if ($Pool) {
  $Pool
} elseif ($env:WORKER_POOL) {
  $env:WORKER_POOL
} else {
  "solo"
}
$resolvedWorkerName = if ($WorkerName) {
  $WorkerName
} elseif ($env:WORKER_NAME) {
  $env:WORKER_NAME
} else {
  "webagent-worker"
}

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

& $python -m celery -A app.workers.celery_app.celery_app worker `
  --hostname="$resolvedWorkerName@%h" `
  --loglevel=info `
  --concurrency=$workerConcurrency `
  --queues=$workerQueues `
  --pool=$workerPool
