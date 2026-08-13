[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw 'Missing .venv. Run ./scripts/bootstrap.ps1 first.'
}

Push-Location $ProjectRoot
try {
    $PreviousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & $Python scripts/verify_sdk.py
    if ($LASTEXITCODE -ne 0) { throw 'SDK integrity verification failed.' }
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
}
finally {
    $env:PYTHONDONTWRITEBYTECODE = $PreviousBytecodeSetting
    Pop-Location
}
