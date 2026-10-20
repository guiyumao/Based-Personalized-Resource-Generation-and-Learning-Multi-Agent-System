$DeployRoot = $PSScriptRoot
$ProjectRoot = (Resolve-Path (Join-Path $DeployRoot '..\..')).Path
$sha = [System.Security.Cryptography.SHA256]::Create()
try { $digest = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($ProjectRoot)) } finally { $sha.Dispose() }
$ProjectTag = [BitConverter]::ToString($digest[0..5]).Replace('-', '').ToLowerInvariant()
# nginx/Windows uses ANSI filesystem paths; a Chinese project directory cannot
# be its prefix. Keep generated files under a short local ASCII path instead.
$RuntimeRoot = Join-Path $env:LOCALAPPDATA "learning-sakurafrp\$ProjectTag"
$NginxExe = ''
$PythonExe = 'python'
$userConfig = Join-Path $DeployRoot 'config.ps1'
if (Test-Path -LiteralPath $userConfig) { . $userConfig }

$Services = @(
    @{ Name = 'user-service'; Segment = 'user'; Port = 8001; App = 'services.user_service.app.main:app' },
    @{ Name = 'agent-service'; Segment = 'agent'; Port = 8002; App = 'services.agent_service.app.main:app' },
    @{ Name = 'resource-service'; Segment = 'resource'; Port = 8003; App = 'services.resource_service.app.main:app' },
    @{ Name = 'evaluation-service'; Segment = 'evaluation'; Port = 8004; App = 'services.evaluation_service.app.main:app' },
    @{ Name = 'teacher-service'; Segment = 'teacher'; Port = 8005; App = 'services.teacher_service.app.main:app' },
    @{ Name = 'system-service'; Segment = 'system'; Port = 8006; App = 'services.system_service.app.main:app' }
)

function Get-NginxExe {
    $candidate = if ($env:NGINX_EXE) { $env:NGINX_EXE } elseif ($NginxExe) { $NginxExe } else { (Get-Command nginx.exe -ErrorAction SilentlyContinue).Source }
    if (-not $candidate -or -not (Test-Path -LiteralPath $candidate)) {
        throw '未找到 nginx.exe。请从 nginx.org 下载 Windows 版，在 config.ps1 设置 $NginxExe。'
    }
    return (Resolve-Path -LiteralPath $candidate).Path
}

function Get-PythonExe {
    $candidate = (Get-Command $PythonExe -ErrorAction SilentlyContinue).Source
    if (-not $candidate) { throw "未找到 Python: $PythonExe" }
    return $candidate
}

function Get-NginxPrefix { return ($RuntimeRoot.Replace('\', '/') + '/') }

function Initialize-Runtime {
    $nginx = Get-NginxExe
    $mime = Join-Path (Split-Path -Parent $nginx) 'conf\mime.types'
    if (-not (Test-Path -LiteralPath $mime)) { throw "缺少 Nginx mime.types: $mime" }
    $dist = Join-Path $ProjectRoot 'web-app\dist'
    if (-not (Test-Path -LiteralPath (Join-Path $dist 'index.html'))) { throw '前端尚未构建。先运行 build.ps1。' }
    foreach ($folder in @('conf', 'html', 'logs', 'temp')) { New-Item -ItemType Directory -Path (Join-Path $RuntimeRoot $folder) -Force | Out-Null }
    Copy-Item -LiteralPath (Join-Path $DeployRoot 'nginx.conf') -Destination (Join-Path $RuntimeRoot 'conf\nginx.conf') -Force
    Copy-Item -LiteralPath (Join-Path $DeployRoot 'proxy-common.conf') -Destination (Join-Path $RuntimeRoot 'conf\proxy-common.conf') -Force
    Copy-Item -LiteralPath $mime -Destination (Join-Path $RuntimeRoot 'conf\mime.types') -Force
    Copy-Item -Path (Join-Path $dist '*') -Destination (Join-Path $RuntimeRoot 'html') -Recurse -Force
    return $nginx
}

function Test-ServiceHealth($service, [switch]$ThroughGateway) {
    $url = if ($ThroughGateway) { "http://127.0.0.1/api/$($service.Segment)/health" } else { "http://127.0.0.1:$($service.Port)/health" }
    try {
        $result = Invoke-RestMethod -Uri $url -TimeoutSec 5
        return ($result.status -eq 'ok' -and $result.service -eq $service.Name)
    } catch { return $false }
}

function Get-ManagedState {
    $path = Join-Path $RuntimeRoot 'processes.json'
    if (Test-Path -LiteralPath $path) { return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
    return [pscustomobject]@{ services = @(); nginxPid = $null }
}

function Save-ManagedState($state) {
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $RuntimeRoot 'processes.json') -Encoding UTF8
}
