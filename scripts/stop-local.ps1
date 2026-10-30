$ErrorActionPreference='Stop'
$projectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime=Join-Path $projectRoot '.local/operations'
$registry=Join-Path $runtime 'processes.json'
if (-not (Test-Path $registry)) { throw 'No recorded startup to stop' }
$record=Get-Content $registry | ConvertFrom-Json
New-Item -ItemType File -Force -Path (Join-Path $runtime 'worker.stop') | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $runtime 'api.stop') | Out-Null
foreach ($entry in @($record.api_launcher,$record.supervisor_launcher)) {
 if ($entry) { $process=Get-Process -Id $entry -ErrorAction SilentlyContinue; if ($process -and -not $process.WaitForExit(60000)) { throw 'Graceful drain timed out; inspect active work. No forced kill was performed.' } }
}
if ($record.web) {
 $webProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$($record.web)"
 if ($webProcess -and $webProcess.CommandLine -like '*node_modules/vite/bin/vite.js*preview*') { Stop-Process -Id $record.web }
 elseif ($webProcess) { throw 'Recorded frontend PID belongs to another process; stop refused' }
}
Remove-Item -LiteralPath $registry
Write-Output 'Application processes stopped. PostgreSQL stays running to preserve other clients.'
