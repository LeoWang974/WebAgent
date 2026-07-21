$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $repoRoot "runtime"
$stdoutLog = Join-Path $runtimeRoot "openclaw-gateway.log"
$stderrLog = Join-Path $runtimeRoot "openclaw-gateway.err.log"
$startScript = Join-Path $runtimeRoot "start-openclaw-gateway.sh"
$openclawSkillsDir = Join-Path $runtimeRoot "openclaw-skills"

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $openclawSkillsDir | Out-Null

$existing = wsl.exe -- bash -lc "ss -ltn | grep -q ':18789 ' && echo running || true"
if (($existing | Out-String).Trim() -eq "running") {
  Write-Host "OpenClaw Gateway is already listening on ws://127.0.0.1:18789"
  exit 0
}

$script = @'
#!/usr/bin/env bash
set -e
export PATH="$HOME/.local/bin:$PATH"

for __f in ~/.hermes/.env ~/.openclaw/.env; do
  [ -f "$__f" ] || continue
  while IFS= read -r __line || [ -n "$__line" ]; do
    __line=${__line%$'\r'}
    case "$__line" in
      ''|\#*) continue ;;
    esac
    __key=${__line%%=*}
    if [[ "$__key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ && "$__key" != PATH ]]; then
      export "$__line"
    fi
  done < "$__f"
done
unset __f __line __key

export OPENCLAW_SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-__OPENCLAW_SKILLS_DIR__}"

exec openclaw gateway run --port 18789 --auth none --bind loopback --force --compact
'@
$openclawSkillsDirWsl = "/mnt/" + $openclawSkillsDir.Substring(0, 1).ToLower() + $openclawSkillsDir.Substring(2).Replace("\", "/")
$script = $script.Replace("__OPENCLAW_SKILLS_DIR__", $openclawSkillsDirWsl)
[System.IO.File]::WriteAllText(
  $startScript,
  $script,
  [System.Text.UTF8Encoding]::new($false)
)
$startScriptWsl = "/mnt/" + $startScript.Substring(0, 1).ToLower() + $startScript.Substring(2).Replace("\", "/")
Write-Host "Starting OpenClaw Gateway: ws://127.0.0.1:18789"
Write-Host "Logs: $stdoutLog"

Start-Process -FilePath "wsl.exe" `
  -ArgumentList @("--", "bash", $startScriptWsl) `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdoutLog `
  -RedirectStandardError $stderrLog `
  -PassThru | Select-Object Id,ProcessName,StartTime

Start-Sleep -Seconds 5

$health = wsl.exe -- bash -lc "openclaw health --json --timeout 5000 || true"
Write-Host $health
