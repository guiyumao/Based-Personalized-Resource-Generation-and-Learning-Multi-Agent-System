$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$failed = $false
try {
    $page = Invoke-WebRequest -Uri 'http://127.0.0.1/' -TimeoutSec 5 -UseBasicParsing
    if ($page.StatusCode -ne 200 -or $page.Content -notmatch '<html') { throw 'HTML 响应异常' }
    Write-Host '统一入口首页：通过'
} catch { Write-Host "统一入口首页：失败 $($_.Exception.Message)"; $failed = $true }
foreach ($service in $Services) {
    $local = Test-ServiceHealth $service
    $gateway = Test-ServiceHealth $service -ThroughGateway
    Write-Host "$($service.Name)：本机=$local，代理=$gateway"
    if (-not $local -or -not $gateway) { $failed = $true }
}
try {
    $page = Invoke-WebRequest -Uri 'http://127.0.0.1/student/dashboard' -TimeoutSec 5 -UseBasicParsing
    if ($page.StatusCode -ne 200 -or $page.Content -notmatch '<html') { throw 'History 回退异常' }
    Write-Host '页面刷新回退：通过'
} catch { Write-Host "页面刷新回退：失败 $($_.Exception.Message)"; $failed = $true }
if ($failed) { exit 1 }
exit 0
