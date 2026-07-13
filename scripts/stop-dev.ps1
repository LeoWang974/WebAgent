$ErrorActionPreference = "Continue"

$ports = @(3002, 8010)

foreach ($port in $ports) {
  $listeners = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" } |
    Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($processId in $listeners) {
    Write-Host "Stopping process tree on port $port (PID $processId)"
    taskkill /PID $processId /T /F | Out-Null
  }
}
