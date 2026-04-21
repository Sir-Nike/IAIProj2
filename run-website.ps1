$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendDir = Join-Path $projectRoot 'frontend'
$siteUrl = 'http://127.0.0.1:5173'

function Import-EnvFile {
    param([string]$FilePath)

    if (-not (Test-Path $FilePath)) {
        return
    }

    Get-Content $FilePath |
        Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } |
        ForEach-Object {
            $key, $value = $_ -split '=', 2
            [Environment]::SetEnvironmentVariable($key, $value, 'Process')
        }
}

if (-not (Test-Path $pythonPath)) {
    throw "Python interpreter not found at $pythonPath. Create the virtual environment first."
}

if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found at $frontendDir."
}

Import-EnvFile (Join-Path $projectRoot '.env.local')
Import-EnvFile (Join-Path $projectRoot '.env')

$backendConnection = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
$frontendConnection = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -First 1

$backendProcess = $null
if ($backendConnection) {
    Write-Host "Backend already running on port 8000 (PID: $($backendConnection.OwningProcess))."
}
else {
    $backendArgs = @(
        '-m', 'uvicorn', 'backend.app.main:app',
        '--host', '127.0.0.1',
        '--port', '8000'
    )
    $backendProcess = Start-Process -FilePath $pythonPath `
        -ArgumentList $backendArgs `
        -WorkingDirectory $projectRoot `
        -PassThru
}

$frontendProcess = $null
if ($frontendConnection) {
    Write-Host "Frontend already running on port 5173 (PID: $($frontendConnection.OwningProcess))."
}
else {
    $npmCommand = if (Get-Command npm.cmd -ErrorAction SilentlyContinue) { 'npm.cmd' } else { 'npm' }
    $frontendCommand = @"
Set-Location '$frontendDir'
if (-not (Test-Path 'node_modules')) { & '$npmCommand' install }
& '$npmCommand' run dev -- --host 127.0.0.1 --port 5173
"@

    $frontendProcess = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $frontendCommand) `
        -WorkingDirectory $frontendDir `
        -PassThru
}

Start-Process $siteUrl

if ($backendProcess) {
    Write-Host "Started backend (PID: $($backendProcess.Id))."
}
if ($frontendProcess) {
    Write-Host "Started frontend (PID: $($frontendProcess.Id))."
}
Write-Host "Website: $siteUrl"
Write-Host "Run this single command from project root: .\\run-website.ps1"