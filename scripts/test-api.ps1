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

$unitTests = @(
  "tests/test_agent_adapter_resolution.py",
  "tests/test_artifact_discovery.py",
  "tests/test_artifact_slides.py",
  "tests/test_cleanup.py",
  "tests/test_hermes_adapter.py",
  "tests/test_hermes_env.py",
  "tests/test_hermes_protocol.py",
  "tests/test_model_runtime_config.py",
  "tests/test_model_runtime_health.py",
  "tests/test_openclaw_adapter.py",
  "tests/test_runtime_context_builder.py",
  "tests/test_skill_detection.py",
  "tests/test_skill_resolution.py",
  "tests/test_skills_update.py"
)

$integrationTests = @(
  "tests/test_agent_runtime_isolation.py",
  "tests/test_api_integration.py"
)

switch ($Group) {
  "unit" { $selectedTests = $unitTests }
  "integration" { $selectedTests = $integrationTests }
  "all" { $selectedTests = $unitTests + $integrationTests }
}

Set-Location -LiteralPath $apiRoot

$pytestArgs = @("-m", "pytest") + $selectedTests + @("-q", "--durations=10")
if ($ExtraArgs.Trim()) {
  $pytestArgs += $ExtraArgs.Trim().Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries)
}

& $python @pytestArgs
