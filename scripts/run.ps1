[CmdletBinding()]
param(
    [ValidateSet('deterministic', 'gpt_oss', 'gemma')]
    [string]$Agent = 'deterministic',
    [string]$Attack = 'attacks/00_static_marker/attack.py',
    [double]$BudgetSeconds = 30,
    [int]$CandidateCount = 32,
    [string]$ModelPath,
    [int]$GpuLayers = -1,
    [string]$TensorSplit
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw 'Missing .venv. Run ./scripts/bootstrap.ps1 first.'
}

$Arguments = @(
    'scripts/evaluate_local.py',
    '--agent', $Agent,
    '--attack', $Attack,
    '--budget-s', $BudgetSeconds,
    '--candidate-count', $CandidateCount,
    '--gpu-layers', $GpuLayers
)
if ($ModelPath) {
    $Arguments += @('--model-path', $ModelPath)
}
if ($TensorSplit) {
    $Arguments += @('--tensor-split', $TensorSplit)
}

Push-Location $ProjectRoot
try {
    $PreviousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Local evaluation failed.' }
}
finally {
    $env:PYTHONDONTWRITEBYTECODE = $PreviousBytecodeSetting
    Pop-Location
}
