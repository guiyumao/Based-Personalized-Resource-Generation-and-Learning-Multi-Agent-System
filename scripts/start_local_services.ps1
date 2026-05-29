$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$services = @(
    @{
        Name = "user-service"
        Port = 8001
        Command = "python -m uvicorn services.user_service.app.main:app --host 127.0.0.1 --port 8001"
    },
    @{
        Name = "agent-service"
        Port = 8002
        Command = "python -m uvicorn services.agent_service.app.main:app --host 127.0.0.1 --port 8002"
    },
    @{
        Name = "evaluation-service"
        Port = 8004
        Command = "python -m uvicorn services.evaluation_service.app.main:app --host 127.0.0.1 --port 8004"
    },
    @{
        Name = "teacher-service"
        Port = 8005
        Command = "python -m uvicorn services.teacher_service.app.main:app --host 127.0.0.1 --port 8005"
    },
    @{
        Name = "system-service"
        Port = 8006
        Command = "python -m uvicorn services.system_service.app.main:app --host 127.0.0.1 --port 8006"
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
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$root'; $($service.Command)"
    )

    Start-Sleep -Seconds 2
}

if (-not (Test-PortListening -Port 5175)) {
    Write-Host "Starting web-app on http://127.0.0.1:5175 ..."
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$root\\web-app'; npm run dev"
    )
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
