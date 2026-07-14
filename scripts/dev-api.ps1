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

& $python -m uvicorn app.main:app --host 127.0.0.1 --port $apiPort --log-level info
