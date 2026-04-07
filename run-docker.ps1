$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker is not available on PATH.'
}

$envFile = Join-Path $projectRoot '.env'
if (-not $env:HF_TOKEN -and -not (Test-Path $envFile)) {
    throw 'HF_TOKEN is required for the backend image build. Set $env:HF_TOKEN or create a .env file from .env.example before running this launcher.'
}

Push-Location $projectRoot
try {
    docker compose up --build
}
finally {
    Pop-Location
}