$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$services = @(
    @{
        Name = "user-service"
        Port = 8001
        App = "services.user_service.app.main:app"
    },
    @{
        Name = "agent-service"
        Port = 8002
        App = "services.agent_service.app.main:app"
    },
    @{
        Name = "evaluation-service"
        Port = 8004
        App = "services.evaluation_service.app.main:app"
    },
    @{
        Name = "teacher-service"
        Port = 8005
        App = "services.teacher_service.app.main:app"
    },
    @{
        Name = "system-service"
        Port = 8006
        App = "services.system_service.app.main:app"
    },
    @{
        Name = "agent-service-qa-compat"
        Port = 8007
        App = "services.agent_service.app.main:app"
    }
)

function Test-PortListening {
    param(
        [int]$Port
    )

    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $connection
}

foreach ($service in $services) {
    if (Test-PortListening -Port $service.Port) {
        Write-Host "$($service.Name) already listening on $($service.Port), skip."
        continue
    }

    Write-Host "Starting $($service.Name) on port $($service.Port)..."
    $stdoutLog = Join-Path $root "$($service.Name).stdout.log"
    $stderrLog = Join-Path $root "$($service.Name).stderr.log"
    Start-Process python -ArgumentList @(
        "-m",
        "uvicorn",
        $service.App,
        "--host",
        "127.0.0.1",
        "--port",
        "$($service.Port)"
    ) -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

    Start-Sleep -Seconds 2
}

if (-not (Test-PortListening -Port 5175)) {
    Write-Host "Starting web-app on http://127.0.0.1:5175 ..."
    $webRoot = Join-Path $root "web-app"
    $webStdoutLog = Join-Path $root "web-app.stdout.log"
    $webStderrLog = Join-Path $root "web-app.stderr.log"
    Start-Process npm.cmd -ArgumentList @("run", "dev") `
        -WorkingDirectory $webRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $webStdoutLog `
        -RedirectStandardError $webStderrLog
}
else {
    Write-Host "web-app already listening on 5175, skip."
}

Write-Host ""
Write-Host "Startup requests sent. Verify with:"
Write-Host "  http://127.0.0.1:5175"
Write-Host "  http://127.0.0.1:8001/health"
Write-Host "  http://127.0.0.1:8002/health"
Write-Host "  http://127.0.0.1:8004/health"
Write-Host "  http://127.0.0.1:8005/health"
Write-Host "  http://127.0.0.1:8006/health"
Write-Host "  http://127.0.0.1:8007/health"
