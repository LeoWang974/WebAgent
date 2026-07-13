$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

Start-Process powershell.exe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $PSScriptRoot "dev-api.ps1")
) -WindowStyle Normal

Start-Process powershell.exe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $PSScriptRoot "dev-web.ps1")
) -WindowStyle Normal

Write-Host "WebAgent dev services are starting."
Write-Host "API: http://127.0.0.1:8010/api/health"
Write-Host "Web: http://localhost:3002/app"
