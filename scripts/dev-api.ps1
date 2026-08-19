# File purpose: Automates the dev api development, deployment, or maintenance workflow.
# Main declarations: Stop-ProcessTreeByPort handles stop process tree by port.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "services\api"
$envFile = Join-Path $apiRoot ".env"
$envExample = Join-Path $apiRoot ".env.example"
$apiPort = 8010

function Stop-ProcessTreeByPort {
  param([int]$Port)

  $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($processId in $listeners) {
    if ($processId -and $processId -ne $PID) {
      Write-Host "Stopping stale API process on port $Port (PID $processId)"
      taskkill /PID $processId /T /F | Out-Null
    }
  }
}

if (-not (Test-Path -LiteralPath $envFile) -and (Test-Path -LiteralPath $envExample)) {
  Copy-Item -LiteralPath $envExample -Destination $envFile
}

Stop-ProcessTreeByPort -Port $apiPort

Set-Location -LiteralPath $apiRoot
$env:PYTHONUNBUFFERED = "1"

$python = Join-Path $apiRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend venv not found: $python"
}

if (-not $env:MODEL_CONFIG_ENCRYPTION_KEY) {
  $secretDirectory = Join-Path $repoRoot "runtime\secrets"
  $secretFile = Join-Path $secretDirectory "model-config.key"
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

Write-Host "Applying database migrations..."
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
  throw "Database migration failed with exit code $LASTEXITCODE"
}

Write-Host "Migrating stored model credentials..."
& $python scripts/migrate_model_secrets.py --apply
if ($LASTEXITCODE -ne 0) {
  throw "Model credential migration failed with exit code $LASTEXITCODE"
}

& $python -m uvicorn app.main:app --host 127.0.0.1 --port $apiPort --log-level info
