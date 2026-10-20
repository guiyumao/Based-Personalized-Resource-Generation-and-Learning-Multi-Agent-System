$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'stop.ps1')
if ($LASTEXITCODE -ne 0) { throw '停止失败。' }
Start-Sleep -Seconds 2
& (Join-Path $PSScriptRoot 'start.ps1')
