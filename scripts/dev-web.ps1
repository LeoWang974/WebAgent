$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "apps\web"
$envFile = Join-Path $webRoot ".env.local"
$envExample = Join-Path $webRoot ".env.local.example"
$webPort = 3002

function Stop-ProcessTreeByPort {
  param([int]$Port)

  $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($processId in $listeners) {
    if ($processId -and $processId -ne $PID) {
      Write-Host "Stopping stale web process on port $Port (PID $processId)"
      taskkill /PID $processId /T /F | Out-Null
    }
  }
}

if (-not (Test-Path -LiteralPath $envFile) -and (Test-Path -LiteralPath $envExample)) {
  Copy-Item -LiteralPath $envExample -Destination $envFile
}

Stop-ProcessTreeByPort -Port $webPort

Set-Location -LiteralPath $repoRoot
# Clean only before the dev server starts. Do not delete .next while Next.js is running.
pnpm --filter web run clean
pnpm --filter web exec next dev --port $webPort
