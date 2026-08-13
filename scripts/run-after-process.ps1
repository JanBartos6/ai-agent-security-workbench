[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [int]$WaitForProcessId,
    [ValidateSet('deterministic', 'gpt_oss', 'gemma')]
    [string]$Agent = 'gpt_oss',
    [Parameter(Mandatory)]
    [string]$Attack,
    [double]$BudgetSeconds = 3600,
    [int]$CandidateCount = 200,
    [int]$GpuLayers = -1,
    [string]$TensorSplit
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunsRoot = Join-Path $ProjectRoot 'runs'
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$RunScript = Join-Path $PSScriptRoot 'run.ps1'

Write-Output "Waiting for process $WaitForProcessId before starting $Attack"
while (Get-Process -Id $WaitForProcessId -ErrorAction SilentlyContinue) {
    Start-Sleep -Seconds 15
}

$StartedAt = Get-Date
$RunArguments = @{
    Agent = $Agent
    Attack = $Attack
    BudgetSeconds = $BudgetSeconds
    CandidateCount = $CandidateCount
    GpuLayers = $GpuLayers
}
if ($TensorSplit) {
    $RunArguments.TensorSplit = $TensorSplit
}

& $RunScript @RunArguments
if ($LASTEXITCODE -ne 0) {
    throw 'Queued local evaluation failed.'
}

$CompletedRun = Get-ChildItem -Path $RunsRoot -Directory |
    Where-Object {
        $_.Name -match '^\d{8}T\d{6}Z$' -and
        $_.LastWriteTime -ge $StartedAt -and
        (Test-Path (Join-Path $_.FullName 'replays.json'))
    } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $CompletedRun) {
    throw 'Evaluation completed, but its run directory could not be identified.'
}

$PreviousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    & $Python (Join-Path $PSScriptRoot 'analyze_run.py') $CompletedRun.FullName --group-by requested_calls style
    if ($LASTEXITCODE -ne 0) {
        throw 'Queued run completed, but analysis failed.'
    }
}
finally {
    $env:PYTHONDONTWRITEBYTECODE = $PreviousBytecodeSetting
}

Write-Output "Queued experiment complete: $($CompletedRun.FullName)"
