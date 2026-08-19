# File purpose: Automates the dev all development, deployment, or maintenance workflow.
# Main declarations: this file contains declarative configuration or re-exports and has no
# callable declarations.

$ErrorActionPreference = "Stop"

Start-Process powershell.exe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $PSScriptRoot "dev-api.ps1")
) -WindowStyle Normal

Start-Process powershell.exe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $PSScriptRoot "api-worker.ps1")
) -WindowStyle Normal

Start-Process powershell.exe -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $PSScriptRoot "dev-web.ps1")
) -WindowStyle Normal

Write-Host "WebAgent dev services are starting."
Write-Host "API: http://127.0.0.1:8010/api/health"
Write-Host "Web: http://localhost:3000/app"
Write-Host "Each child window owns its process; close the window or press Ctrl+C to stop it."
