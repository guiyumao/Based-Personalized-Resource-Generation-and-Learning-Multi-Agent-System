param(
  [Parameter(Mandatory=$true)][string]$RuntimeDirectory,
  [Parameter(Mandatory=$true)][string]$EvidenceDirectory
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$runtimeRoot = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
if (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot 'runtime.sqlite'))) { throw 'Existing runtime database required' }
$manifest = Get-Content -LiteralPath (Join-Path $runtimeRoot 'processes.json') -Raw | ConvertFrom-Json
$services = @(
  @{Name='resource';Port=8003;Module='services.resource_service.app.main:app'},
  @{Name='system';Port=8006;Module='services.system_service.app.main:app'}
)
# Verify every target before interrupting either service.
foreach ($service in $services) {
  $record = $manifest | Where-Object Name -eq $service.Name
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.PID)"
  if (-not $process -or $process.CommandLine -notlike "*$($service.Module)*--port $($service.Port)*") { throw "Unexpected $($service.Name) process; no automatic replacement" }
  $service.PreviousPID = $record.PID
}
New-Item -ItemType Directory -Path $EvidenceDirectory -ErrorAction Stop | Out-Null
$evidenceRoot = (Resolve-Path -LiteralPath $EvidenceDirectory).Path
$env:DATABASE_URL = 'sqlite+pysqlite:///' + (Join-Path $runtimeRoot 'runtime.sqlite').Replace('\','/')
$env:CORS_ALLOW_ORIGINS = 'http://127.0.0.1:5175,http://localhost:5175'
$env:LLM_PREWARM_ENABLED = 'false'
$env:GRAPH_LLM_ENRICH_ENABLED = 'false'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$results = @()
foreach ($service in $services) {
  Stop-Process -Id $service.PreviousPID
  Wait-Process -Id $service.PreviousPID -ErrorAction SilentlyContinue
  # The existing schema was already bootstrapped. Disable lifespan during this
  # targeted refresh to avoid any bootstrap DDL or data writes to the live DB.
  $process = Start-Process -FilePath 'C:\Users\wdx\anaconda3\python.exe' -ArgumentList @('-m','uvicorn',$service.Module,'--host','127.0.0.1','--port',"$($service.Port)",'--lifespan','off') -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $evidenceRoot "$($service.Name).stdout.log") -RedirectStandardError (Join-Path $evidenceRoot "$($service.Name).stderr.log") -PassThru
  $ready = $false
  for ($attempt=0; $attempt -lt 40; $attempt++) {
    try {
      $health = Invoke-RestMethod "http://127.0.0.1:$($service.Port)/health" -TimeoutSec 1
      if ($health.status -eq 'ok') { $ready = $true; break }
    } catch {}
    if ($process.HasExited) { throw "$($service.Name) exited; inspect evidence logs" }
    Start-Sleep -Milliseconds 250
  }
  if (-not $ready) { throw "$($service.Name) failed health check" }
  $results += [pscustomobject]@{Name=$service.Name;Port=$service.Port;PreviousPID=$service.PreviousPID;PID=$process.Id;Health='ok';Lifespan='off';DatabaseWritesPerformed=$false}
}
$results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidenceRoot 'processes.json') -Encoding utf8
$results | Select-Object Name,Port,PreviousPID,PID,Health,Lifespan
