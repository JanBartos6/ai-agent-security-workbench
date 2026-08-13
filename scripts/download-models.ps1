[CmdletBinding()]
param(
    [ValidateSet('gpt_oss', 'gemma', 'all')]
    [string]$Model = 'all'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw 'Missing .venv. Run ./scripts/bootstrap.ps1 first.'
}

Push-Location $ProjectRoot
try {
    & $Python scripts/download_models.py --model $Model --output-dir models
    if ($LASTEXITCODE -ne 0) { throw 'Model download or hash verification failed.' }
}
finally {
    Pop-Location
}

