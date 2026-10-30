param(
 [Parameter(Mandatory=$true)][string]$Python,
 [Parameter(Mandatory=$true)][string]$PostgresBin,
 [Parameter(Mandatory=$true)][string]$DataDirectory,
 [int]$DatabasePort=55432,
 [int]$ApiPort=8000,
 [int]$WebPort=5173,
 [switch]$Migrate
)
$ErrorActionPreference='Stop'
$projectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot=Join-Path $projectRoot 'apps/backend'
$frontendRoot=Join-Path $projectRoot 'apps/frontend'
$runtime=Join-Path $projectRoot '.local/operations'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$mutex=[System.Threading.Mutex]::new($false,'Local\JobSearchIntelligenceStartup')
if (-not $mutex.WaitOne(0)) { throw 'Another startup is in progress' }
try {
 if (Test-Path (Join-Path $runtime 'processes.json')) { throw 'Process registry exists. Inspect or stop the recorded environment before starting again.' }
 if (-not (Test-Path (Join-Path $DataDirectory 'PG_VERSION'))) { throw 'Existing PostgreSQL data directory required; startup never initializes a cluster' }
 & (Join-Path $PostgresBin 'pg_ctl.exe') -D $DataDirectory status | Out-Null
 if ($LASTEXITCODE -ne 0) {
  & (Join-Path $PostgresBin 'pg_ctl.exe') -D $DataDirectory -l (Join-Path $runtime 'postgres.log') -o "-h 127.0.0.1 -p $DatabasePort" start
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed' }
 }
 Push-Location $backendRoot
 try {
  & $Python -c "from app.core.config import settings; from app.db.session import engine; from sqlalchemy import text; c=engine.connect(); c.execute(text('SELECT 1')); c.close(); print('Configuration and database reachable')"
  if ($LASTEXITCODE -ne 0) { throw 'Configuration or database validation failed' }
  if ($Migrate) { & $Python -m alembic upgrade head; if ($LASTEXITCODE -ne 0) { throw 'Explicit migration failed' } }
  & $Python -c "from app.db.session import engine; from sqlalchemy import text; c=engine.connect(); assert c.scalar(text('SELECT version_num FROM alembic_version'))=='0007_local_operations'; c.close()"
  if ($LASTEXITCODE -ne 0) { throw 'Schema mismatch. Review migrations, backup, then explicitly request -Migrate.' }
 } finally { Pop-Location }
 foreach ($port in @($ApiPort,$WebPort)) {
  $probe=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,$port)
  try { $probe.Start() } finally { $probe.Stop() }
 }
 if (-not (Test-Path (Join-Path $frontendRoot 'dist/index.html'))) { throw 'Build frontend first with npm run build' }
 foreach ($marker in @('api.stop','worker.stop')) {
  $path=Join-Path $runtime $marker
  if (Test-Path $path) { Remove-Item -LiteralPath $path }
 }
 $api=Start-Process -FilePath $Python -ArgumentList @('-m','app.operations.api_process',"`"$(Join-Path $runtime 'api.stop')`"",$ApiPort) -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'api.log') -RedirectStandardError (Join-Path $runtime 'api-errors.log')
 @{api_launcher=$api.Id;state='starting'} | ConvertTo-Json | Set-Content (Join-Path $runtime 'processes.json')
 $ready=$false
 for ($i=0;$i -lt 30;$i++) { try { Invoke-WebRequest "http://127.0.0.1:$ApiPort/api/v1/health/ready" -TimeoutSec 2 | Out-Null; $ready=$true;break } catch { Start-Sleep -Milliseconds 500 } }
 if (-not $ready) { throw 'Backend readiness failed; partial startup recorded for safe shutdown' }
 $worker=Start-Process -FilePath $Python -ArgumentList @('-m','app.operations.supervisor',"`"$runtime`"") -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'supervisor.log') -RedirectStandardError (Join-Path $runtime 'supervisor-errors.log')
 $web=Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @('node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port',$WebPort,'--strictPort') -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'web.log') -RedirectStandardError (Join-Path $runtime 'web-errors.log')
 @{api_launcher=$api.Id;supervisor_launcher=$worker.Id;web=$web.Id;state='started';api_port=$ApiPort;web_port=$WebPort} | ConvertTo-Json | Set-Content (Join-Path $runtime 'processes.json')
 $verified=$false
 for ($i=0;$i -lt 40;$i++) {
  try {
   Invoke-WebRequest "http://127.0.0.1:$WebPort" -TimeoutSec 2 | Out-Null
   $workerState=Get-Content (Join-Path $runtime 'worker-record.json') -ErrorAction Stop | ConvertFrom-Json
   if ($workerState.status -in @('idle','running')) { $verified=$true;break }
  } catch { }
  Start-Sleep -Milliseconds 500
 }
 if (-not $verified) { throw 'Frontend or worker readiness was not established; inspect the partial startup registry' }
 Write-Output "Backend: http://127.0.0.1:$ApiPort ; Frontend: http://127.0.0.1:$WebPort. Inspect worker database heartbeat; process presence is not health."
} finally { $mutex.ReleaseMutex();$mutex.Dispose() }
