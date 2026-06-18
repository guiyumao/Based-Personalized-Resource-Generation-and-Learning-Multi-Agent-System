$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $root "scripts\start_local_services.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Cannot find startup script: $scriptPath"
}

Write-Host "Launching local services with one command..."
& powershell -ExecutionPolicy Bypass -File $scriptPath
