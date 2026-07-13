$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $repoRoot "apps\web"
$envFile = Join-Path $webRoot ".env.local"
$envExample = Join-Path $webRoot ".env.local.example"

if (-not (Test-Path -LiteralPath $envFile) -and (Test-Path -LiteralPath $envExample)) {
  Copy-Item -LiteralPath $envExample -Destination $envFile
}

Set-Location -LiteralPath $repoRoot
pnpm --filter web dev -- --port 3002
