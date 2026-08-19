# File purpose: Automates the test api development, deployment, or maintenance workflow.
# Main declarations: this file contains declarative configuration or re-exports and has no
# callable declarations.

param(
  [ValidateSet("unit", "integration", "all")]
  [string]$Group = "unit",

  [string]$ExtraArgs = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "services\api"
$python = Join-Path $apiRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend venv not found: $python"
}

$integrationTests = @(
  "tests/test_agent_runtime_isolation.py",
  "tests/test_api_integration.py"
)

$allTests = Get-ChildItem -LiteralPath (Join-Path $apiRoot "tests") -Filter "test_*.py" |
  ForEach-Object { "tests/$($_.Name)" } |
  Sort-Object
$unitTests = @($allTests | Where-Object { $integrationTests -notcontains $_ })

switch ($Group) {
  "unit" { $selectedTests = $unitTests }
  "integration" { $selectedTests = $integrationTests }
  "all" { $selectedTests = $allTests }
}

Set-Location -LiteralPath $apiRoot

$pytestArgs = @("-m", "pytest") + $selectedTests + @("-q", "--durations=10")
if ($ExtraArgs.Trim()) {
  $pytestArgs += $ExtraArgs.Trim().Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
}

& $python @pytestArgs
