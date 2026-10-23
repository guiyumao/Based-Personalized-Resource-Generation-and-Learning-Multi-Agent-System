$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$hostAddress = if ($env:LOCAL_SERVICE_HOST) { $env:LOCAL_SERVICE_HOST } else { "127.0.0.1" }
$frontendHost = if ($env:FRONTEND_HOST) { $env:FRONTEND_HOST } else { $hostAddress }
$frontendPort = if ($env:FRONTEND_PORT) { [int]$env:FRONTEND_PORT } else { 5175 }
$serviceLogRoot = Join-Path $root "logs\services"
$frontendLogRoot = Join-Path $root "logs\frontend"
New-Item -ItemType Directory -Force -Path $serviceLogRoot, $frontendLogRoot | Out-Null

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
        Reload = $true
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
        $listeners = Get-NetTCPConnection -State Listen -LocalPort $service.Port -ErrorAction SilentlyContinue
        $managedProcesses = foreach ($listener in $listeners) {
            $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
            if ($processInfo -and $processInfo.CommandLine -like "*$($service.App)*" -and $processInfo.CommandLine -like "*--port $($service.Port)*") {
                $processInfo
            }
        }

        $needsReloadRestart = $service.Reload -and @($managedProcesses).Count -gt 0 -and @($managedProcesses | Where-Object { $_.CommandLine -notlike "*--reload*" }).Count -gt 0
        if ($needsReloadRestart) {
            foreach ($processInfo in $managedProcesses) {
                Write-Host "Restarting stale $($service.Name) process $($processInfo.ProcessId) with reload enabled..."
                Stop-Process -Id $processInfo.ProcessId -Force
                Wait-Process -Id $processInfo.ProcessId -ErrorAction SilentlyContinue
            }
        }
        elseif ($service.Reload -and @($managedProcesses).Count -gt 0) {
            Write-Host "$($service.Name) already running with reload enabled on $($service.Port), skip."
            continue
        }

        if (Test-PortListening -Port $service.Port) {
            Write-Host "$($service.Name) already listening on $($service.Port); no managed stale process could be safely restarted, skip."
            continue
        }
    }

    Write-Host "Starting $($service.Name) on port $($service.Port)..."
    $stdoutLog = Join-Path $serviceLogRoot "$($service.Name).stdout.log"
    $stderrLog = Join-Path $serviceLogRoot "$($service.Name).stderr.log"
    $arguments = @(
        "-m",
        "uvicorn",
        $service.App,
        "--host",
        $hostAddress,
        "--port",
        "$($service.Port)"
    )
    if ($service.Reload) {
        $arguments += @("--reload", "--reload-dir", "services", "--reload-dir", "common", "--reload-dir", "scripts")
    }
    Start-Process python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

    Start-Sleep -Seconds 2
}

$workerProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match 'services\.agent_service\.app\.services\.(assistant_worker|knowledge_worker)'
})
$assistantExecutionMode = (& python -c "from common.config import get_settings; print(get_settings().assistant_task_execution_mode)").Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to resolve assistant task execution mode" }
if ($assistantExecutionMode -eq "worker" -and -not @($workerProcesses | Where-Object {
    $_.CommandLine -match 'services\.agent_service\.app\.services\.assistant_worker'
}).Count) {
    Write-Host "Starting assistant-worker for durable workspace generation..."
    Start-Process python -ArgumentList @("-m", "services.agent_service.app.services.assistant_worker", "--skip-schema-bootstrap") `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $serviceLogRoot "assistant-worker.stdout.log") `
        -RedirectStandardError (Join-Path $serviceLogRoot "assistant-worker.stderr.log")
    $workerProcesses = @("assistant-worker-start-requested")
}
if ($workerProcesses.Count -eq 0 -and $env:KNOWLEDGE_WORKER_ENABLED -ne "false") {
    Write-Host "Starting knowledge-worker for queued and scheduled knowledge tasks..."
    Start-Process python -ArgumentList @("-m", "services.agent_service.app.services.knowledge_worker") `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $serviceLogRoot "knowledge-worker.stdout.log") `
        -RedirectStandardError (Join-Path $serviceLogRoot "knowledge-worker.stderr.log")
}
elseif ($workerProcesses.Count -gt 0) {
    Write-Host "An assistant or knowledge worker is already running; skip knowledge-worker."
}

# Async coordinator worker: consumes the RabbitMQ path_generation queue and
# also sweeps queued rows when the broker is unavailable.
$pathWorkerProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match 'services\.agent_service\.app\.services\.path_worker'
})
if ($pathWorkerProcesses.Count -eq 0 -and $env:PATH_WORKER_ENABLED -ne "false") {
    Write-Host "Starting path-worker for async learning-path generation..."
    Start-Process python -ArgumentList @("-m", "services.agent_service.app.services.path_worker") `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $serviceLogRoot "path-worker.stdout.log") `
        -RedirectStandardError (Join-Path $serviceLogRoot "path-worker.stderr.log")
}

if (-not (Test-PortListening -Port $frontendPort)) {
    Write-Host "Starting web-app on http://$($frontendHost):$($frontendPort) ..."
    $webRoot = Join-Path $root "web-app"
    $webStdoutLog = Join-Path $frontendLogRoot "web-app.stdout.log"
    $webStderrLog = Join-Path $frontendLogRoot "web-app.stderr.log"
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
