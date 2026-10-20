$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$state = Get-ManagedState
if ($state.nginxPid) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($state.nginxPid)" -ErrorAction SilentlyContinue
    $prefix = (Get-NginxPrefix).TrimEnd('/')
    if ($process -and $process.Name -eq 'nginx.exe' -and $process.CommandLine -like "*$prefix*") {
        $nginx = Get-NginxExe
        & $nginx -s quit -p (Get-NginxPrefix) -c 'conf/nginx.conf'
        Write-Host '已请求停止本部署脚本启动的 Nginx。'
    }
}
foreach ($entry in @($state.services)) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.pid)" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -like "*$($entry.app)*" -and $process.CommandLine -like '*-m uvicorn*') {
        Stop-Process -Id $entry.pid
        Write-Host "已停止 $($entry.name) PID $($entry.pid)"
    }
}
$state.services = @()
$state.nginxPid = $null
Save-ManagedState $state
Write-Host '未停止任何非本脚本管理的进程；SakuraFrp 隧道请在客户端手动关闭。'
