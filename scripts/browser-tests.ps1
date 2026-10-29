param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'apps\backend'
$frontendRoot = Join-Path $projectRoot 'apps\frontend'
$pythonPath = (Get-Command $Python).Source
$npmPath = (Get-Command 'npm.cmd').Source
$nodePath = (Get-Command 'node.exe').Source
$previousEnvironment = @{}
foreach ($key in @('BROWSER_DATABASE_URL','DATABASE_URL','ALLOWED_ORIGINS','API_TARGET','RESUME_STORAGE_ROOT','BROWSER_TEST_PYTHON')) {
    $previousEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
foreach ($port in @(8001,5174)) {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try { $probe.Start() } catch { throw "Port $port is already in use. Stop the previous test server first." } finally { $probe.Stop() }
}
$env:BROWSER_DATABASE_URL = & $pythonPath -c "from dotenv import dotenv_values; import os; print(os.environ.get('BROWSER_DATABASE_URL') or dotenv_values(r'$projectRoot\.env').get('BROWSER_DATABASE_URL',''))"
if (-not $env:BROWSER_DATABASE_URL.EndsWith('_browser')) { throw 'Configure a disposable BROWSER_DATABASE_URL ending in _browser.' }
$logRoot = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$apiProcess = $null
$webProcess = $null
try {
    Push-Location $backendRoot
    & $pythonPath -m tests.browser_data
    if ($LASTEXITCODE -ne 0) { throw 'Browser fixture setup failed.' }
    Pop-Location
    $env:DATABASE_URL = $env:BROWSER_DATABASE_URL
    $env:RESUME_STORAGE_ROOT = Join-Path $logRoot 'browser-resumes'
    $env:BROWSER_TEST_PYTHON = $pythonPath
    $env:ALLOWED_ORIGINS = '["http://127.0.0.1:5174"]'
    $env:API_TARGET = 'http://127.0.0.1:8001'
    $apiProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8001') -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'browser-api.log') -RedirectStandardError (Join-Path $logRoot 'browser-api-error.log')
    $webProcess = Start-Process -FilePath $nodePath -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5174','--strictPort') -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'browser-web.log') -RedirectStandardError (Join-Path $logRoot 'browser-web-error.log')
    foreach ($uri in @('http://127.0.0.1:8001/api/v1/health/ready','http://127.0.0.1:5174')) {
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            try { Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2 | Out-Null; $ready = $true; break } catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $ready) { throw "Service did not become ready: $uri" }
    }
    Push-Location $frontendRoot
    & $npmPath run test:e2e
    $testExitCode = $LASTEXITCODE
    Pop-Location
    if ($testExitCode -ne 0) { throw 'Browser tests failed; inspect Playwright report.' }
} finally {
    if ($apiProcess -and -not $apiProcess.HasExited) { Stop-Process -Id $apiProcess.Id }
    if ($webProcess -and -not $webProcess.HasExited) { Stop-Process -Id $webProcess.Id }
    foreach ($key in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previousEnvironment[$key], 'Process')
    }
}
