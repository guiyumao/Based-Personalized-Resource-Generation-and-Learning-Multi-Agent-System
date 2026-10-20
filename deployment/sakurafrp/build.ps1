$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw '未找到 npm.cmd，请安装 Node.js。' }
$null = Get-PythonExe
$nginx = Get-NginxExe
Write-Host '构建 Vue 生产包（SakuraFrp 同源 API）...'
Push-Location (Join-Path $ProjectRoot 'web-app')
try {
    & npm.cmd run build:sakurafrp
    if ($LASTEXITCODE -ne 0) { throw "前端构建失败，退出码 $LASTEXITCODE" }
} finally { Pop-Location }

$null = Initialize-Runtime
& $nginx -t -p (Get-NginxPrefix) -c 'conf/nginx.conf'
if ($LASTEXITCODE -ne 0) { throw "Nginx 配置校验失败，退出码 $LASTEXITCODE" }
Write-Host '构建完成：web-app/dist 与 Nginx runtime/html 已就绪。FastAPI 从源码运行，无 JAR 构建。'
