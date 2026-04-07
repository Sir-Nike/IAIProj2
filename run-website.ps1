$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendDir = Join-Path $projectRoot 'frontend'

if (-not (Test-Path $pythonPath)) {
    throw "Python interpreter not found at $pythonPath. Create the virtual environment first."
}

if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found at $frontendDir."
}

$backendArgs = @(
    '-m', 'uvicorn', 'backend.app.main:app',
    '--host', '127.0.0.1',
    '--port', '8000'
)

$backendProcess = Start-Process -FilePath $pythonPath `
    -ArgumentList $backendArgs `
    -WorkingDirectory $projectRoot `
    -PassThru

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

Start-Process 'http://127.0.0.1:5173'

Write-Host "Backend PID: $($backendProcess.Id)"
Write-Host "Frontend PID: $($frontendProcess.Id)"
Write-Host 'The website is starting at http://127.0.0.1:5173'