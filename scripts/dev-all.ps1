# File purpose: Automates the dev all development, deployment, or maintenance workflow.
# Main declarations: this file contains declarative configuration or re-exports and has no
# callable declarations.

$ErrorActionPreference = "Stop"

Start-Process powershell.exe -ArgumentList @(
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $PSScriptRoot "dev-api.ps1")
) -WindowStyle Hidden

foreach ($shortWorkerIndex in 1..2) {
  Start-Process powershell.exe -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "api-worker.ps1"),
    "-Queues", "short-chat",
    "-WorkerName", "webagent-short-$shortWorkerIndex",
    "-Concurrency", "1"
  ) -WindowStyle Hidden
}

foreach ($workerIndex in 1..2) {
  Start-Process powershell.exe -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "api-worker.ps1"),
    "-Queues", "agent-runs",
    "-WorkerName", "webagent-agent-$workerIndex",
    "-Concurrency", "1"
  ) -WindowStyle Hidden
}

Start-Process powershell.exe -ArgumentList @(
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $PSScriptRoot "dev-web.ps1")
) -WindowStyle Hidden

Write-Host "WebAgent dev services are starting."
Write-Host "API: http://127.0.0.1:8010/api/health"
Write-Host "Web: http://localhost:3000/app"
Write-Host "Workers: two short-chat workers and two independent agent-runs workers."
Write-Host "Run scripts/stop-dev.ps1 to stop all development processes."
