# File purpose: Automates the stop dev development, deployment, or maintenance workflow.
# Main declarations: this file contains declarative configuration or re-exports and has no
# callable declarations.

$ErrorActionPreference = "Continue"

$repoRoot = (Split-Path -Parent $PSScriptRoot).ToLowerInvariant()
$ports = @(3000, 8010)

foreach ($port in $ports) {
  $listeners = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" } |
    Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($processId in $listeners) {
    Write-Host "Stopping process tree on port $port (PID $processId)"
    taskkill /PID $processId /T /F | Out-Null
  }
}

$workerProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.ProcessId -ne $PID -and
    $_.CommandLine -and
    $_.CommandLine.ToLowerInvariant().Contains($repoRoot) -and
    $_.CommandLine -match "-m\s+celery"
  } |
  Sort-Object ProcessId -Descending

foreach ($workerProcess in $workerProcesses) {
  Write-Host "Stopping Celery worker process tree (PID $($workerProcess.ProcessId))"
  taskkill /PID $workerProcess.ProcessId /T /F | Out-Null
}
