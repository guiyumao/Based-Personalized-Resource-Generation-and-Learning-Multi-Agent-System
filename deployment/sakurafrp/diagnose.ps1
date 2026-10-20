$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common.ps1')

Write-Host '=== SakuraFrp 本地部署诊断 ==='
foreach ($port in @(80, 8001, 8002, 8003, 8004, 8005, 8006)) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listeners) {
        foreach ($item in $listeners) { Write-Host "端口 $port：$($item.LocalAddress)，PID $($item.OwningProcess)" }
    } else { Write-Host "端口 $port：未监听" }
}
try {
    $nginx = Get-NginxExe
    & $nginx -t -p (Get-NginxPrefix) -c 'conf/nginx.conf'
} catch { Write-Host "Nginx：$($_.Exception.Message)" }
& (Join-Path $PSScriptRoot 'health-check.ps1')
Write-Host "502/503：先检查 $RuntimeRoot\logs 中的服务错误日志；404：核对 /api/{服务名}/ 前缀。"
Write-Host '上传 413：检查 nginx.conf 的 client_max_body_size；AI 超时：检查 agent 服务日志和模型配置。'
Write-Host '公网不可达：检查 SakuraFrp 客户端日志、隧道认证、节点建站规则和远程地址。'
Write-Host '公网 HTTPS：用手机移动网络验证证书和地址；本脚本无法凭本机端口判断公网隧道状态。'
