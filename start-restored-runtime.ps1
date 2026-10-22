$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$dbPath = Join-Path $PSScriptRoot 'artifacts/local-start-20261019/runtime.sqlite'
if (-not (Test-Path -LiteralPath $dbPath)) { throw 'Restore overlay files into the project root first.' }
$env:DATABASE_URL = 'sqlite+pysqlite:///' + $dbPath.Replace('\','/')
$env:ASSISTANT_TASK_EXECUTION_MODE = 'worker'
$env:LLM_PREWARM_ENABLED = 'false'
$env:GRAPH_LLM_ENRICH_ENABLED = 'false'
$env:CORS_ALLOW_ORIGINS = 'http://127.0.0.1:5175,http://localhost:5175'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
& (Join-Path $PSScriptRoot 'start-dev.ps1')
