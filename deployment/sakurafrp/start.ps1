$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$nginx = Initialize-Runtime
& $nginx -t -p (Get-NginxPrefix) -c 'conf/nginx.conf'
if ($LASTEXITCODE -ne 0) { throw 'Nginx 配置校验失败。' }
$python = Get-PythonExe
$state = Get-ManagedState
$managed = @($state.services)

foreach ($service in $Services) {
    if (Test-ServiceHealth $service) { Write-Host "$($service.Name) 已就绪。"; continue }
    $listener = Get-NetTCPConnection -State Listen -LocalPort $service.Port -ErrorAction SilentlyContinue
    if ($listener) { throw "$($service.Port) 已被占用，但 $($service.Name) 健康检查失败。请运行 diagnose.ps1。" }
    $out = Join-Path $RuntimeRoot "logs\$($service.Segment).stdout.log"
    $err = Join-Path $RuntimeRoot "logs\$($service.Segment).stderr.log"
    $process = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', $service.App, '--host', '127.0.0.1', '--port', [string]$service.Port) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    $managed += [pscustomobject]@{ name = $service.Name; app = $service.App; pid = $process.Id }
    $state.services = $managed
    Save-ManagedState $state
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-ServiceHealth $service) { $ready = $true; break }
        if ($process.HasExited) { break }
    }
    if (-not $ready) { throw "$($service.Name) 未就绪，请查看 $err" }
    Write-Host "$($service.Name) 已启动。"
}

$gateway = Get-NetTCPConnection -State Listen -LocalPort 80 -ErrorAction SilentlyContinue
if (-not $gateway) {
    $args = '-p "{0}" -c conf/nginx.conf' -f (Get-NginxPrefix)
    $process = Start-Process -FilePath $nginx -ArgumentList $args -WorkingDirectory $RuntimeRoot -WindowStyle Hidden -PassThru
    $state.nginxPid = $process.Id
    Save-ManagedState $state
    Start-Sleep -Seconds 2
} else {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($gateway[0].OwningProcess)" -ErrorAction SilentlyContinue
    $prefix = (Get-NginxPrefix).TrimEnd('/')
    if (-not $owner -or $owner.Name -ne 'nginx.exe' -or $owner.CommandLine -notlike "*$prefix*") {
        throw '80 端口被非本部署 Nginx 占用。'
    }
    & $nginx -s reload -p (Get-NginxPrefix) -c 'conf/nginx.conf'
    if ($LASTEXITCODE -ne 0) { throw 'Nginx 重新加载失败。' }
}

& (Join-Path $PSScriptRoot 'health-check.ps1')
if ($LASTEXITCODE -ne 0) { throw '统一入口未通过健康检查。' }
Write-Host '本地入口：http://127.0.0.1/；SakuraFrp 隧道需在客户端手动确认上线。'
