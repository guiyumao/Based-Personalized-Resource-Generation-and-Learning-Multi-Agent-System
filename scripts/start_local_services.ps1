$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$hostAddress = if ($env:LOCAL_SERVICE_HOST) { $env:LOCAL_SERVICE_HOST } else { "127.0.0.1" }
$frontendHost = if ($env:FRONTEND_HOST) { $env:FRONTEND_HOST } else { $hostAddress }
$frontendPort = if ($env:FRONTEND_PORT) { [int]$env:FRONTEND_PORT } else { 5175 }

$services = @(
    @{
        Name = "user-service"
        Port = if ($env:USER_SERVICE_PORT) { [int]$env:USER_SERVICE_PORT } else { 8001 }
        App = "services.user_service.app.main:app"
        FrontendEnv = "VITE_USER_API_BASE_URL"
    },
    @{
        Name = "agent-service"
        Port = if ($env:AGENT_SERVICE_PORT) { [int]$env:AGENT_SERVICE_PORT } else { 8002 }
        App = "services.agent_service.app.main:app"
        FrontendEnv = "VITE_AGENT_API_BASE_URL"
    },
    @{
        Name = "resource-service"
        Port = if ($env:RESOURCE_SERVICE_PORT) { [int]$env:RESOURCE_SERVICE_PORT } else { 8003 }
        App = "services.resource_service.app.main:app"
        FrontendEnv = "VITE_RESOURCE_API_BASE_URL"
    },
    @{
        Name = "evaluation-service"
        Port = if ($env:EVALUATION_SERVICE_PORT) { [int]$env:EVALUATION_SERVICE_PORT } else { 8004 }
        App = "services.evaluation_service.app.main:app"
        FrontendEnv = "VITE_EVALUATION_API_BASE_URL"
    },
    @{
        Name = "teacher-service"
        Port = if ($env:TEACHER_SERVICE_PORT) { [int]$env:TEACHER_SERVICE_PORT } else { 8005 }
        App = "services.teacher_service.app.main:app"
        FrontendEnv = "VITE_TEACHER_API_BASE_URL"
    },
    @{
        Name = "system-service"
        Port = if ($env:SYSTEM_SERVICE_PORT) { [int]$env:SYSTEM_SERVICE_PORT } else { 8006 }
        App = "services.system_service.app.main:app"
        FrontendEnv = "VITE_SYSTEM_API_BASE_URL"
    },
    @{
        Name = "agent-service-qa-compat"
        Port = if ($env:AGENT_SERVICE_QA_COMPAT_PORT) { [int]$env:AGENT_SERVICE_QA_COMPAT_PORT } else { 8007 }
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

function Ensure-FrontendEnvFile {
    $webRoot = Join-Path $root "web-app"
    $envLocalPath = Join-Path $webRoot ".env.local"

    if (Test-Path $envLocalPath) {
        return
    }

    Write-Host "Creating web-app/.env.local with local service endpoints..."
    $frontendEnvLines = foreach ($service in $services) {
        if ($service.FrontendEnv) {
            "$($service.FrontendEnv)=http://$($hostAddress):$($service.Port)"
        }
    }
    $frontendEnvLines | Set-Content -Path $envLocalPath -Encoding UTF8
}

Ensure-FrontendEnvFile

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
        $hostAddress,
        "--port",
        "$($service.Port)"
    ) -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

    Start-Sleep -Seconds 2
}

if (-not (Test-PortListening -Port $frontendPort)) {
    Write-Host "Starting web-app on http://$($frontendHost):$($frontendPort) ..."
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
    Write-Host "web-app already listening on $($frontendPort), skip."
}

Write-Host ""
Write-Host "Startup requests sent. Verify with:"
Write-Host "  http://$($frontendHost):$($frontendPort)"
foreach ($service in $services) {
    Write-Host "  http://$($hostAddress):$($service.Port)/health"
}
