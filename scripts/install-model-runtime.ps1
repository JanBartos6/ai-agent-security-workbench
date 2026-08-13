[CmdletBinding()]
param(
    [switch]$Rebuild,
    [ValidateRange(1, 24)]
    [int]$Jobs = 12
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LlamaVersion = '0.3.34'
$WheelDirectory = Join-Path $ProjectRoot 'runs\model-runtime-wheel'
$WheelPattern = "llama_cpp_python-$LlamaVersion-py3-none-win_amd64.whl"

if (-not (Test-Path $Python)) {
    throw 'Missing .venv. Run ./scripts/bootstrap.ps1 first.'
}

New-Item -ItemType Directory -Force -Path $WheelDirectory | Out-Null
$Wheel = Get-ChildItem -Path $WheelDirectory -Filter $WheelPattern -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($Rebuild -or -not $Wheel) {
    $VsWhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path $VsWhere)) { throw 'Visual Studio Installer (vswhere.exe) was not found.' }

    $VsPath = & $VsWhere -version '[17.0,18.0)' -products '*' `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath
    if (-not $VsPath) { throw 'Visual Studio 2022 C++ tools were not found.' }
    $VsPath = @($VsPath)[0]

    $Nvcc = Get-Command nvcc.exe -ErrorAction Stop
    $CudaRoot = Split-Path -Parent (Split-Path -Parent $Nvcc.Source)
    $MsvcVersion = Get-ChildItem (Join-Path $VsPath 'VC\Tools\MSVC') -Directory |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1
    if (-not $MsvcVersion) { throw 'MSVC compiler directory was not found.' }

    $MsvcBin = Join-Path $MsvcVersion.FullName 'bin\HostX64\x64'
    $Compiler = Join-Path $MsvcBin 'cl.exe'
    $VsDevCmd = Join-Path $VsPath 'Common7\Tools\VsDevCmd.bat'
    $NinjaDir = Join-Path $VsPath 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja'

    $KitsRoot = (Get-ItemProperty `
        'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
    $SdkBin = Get-ChildItem (Join-Path $KitsRoot 'bin') -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'x64\rc.exe') } |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1
    if (-not $SdkBin) { throw 'Windows SDK x64 tools were not found.' }
    $SdkBin = Join-Path $SdkBin.FullName 'x64'

    $DriveRoot = [IO.Path]::GetPathRoot($ProjectRoot)
    $BuildTemp = Join-Path $DriveRoot 'lcp-aicomp-build'
    New-Item -ItemType Directory -Force -Path $BuildTemp | Out-Null

    $CmakeArgs = @(
        '-DGGML_CUDA=ON'
        '-DGGML_CUDA_FORCE_MMQ=ON'
        '-DGGML_NATIVE=OFF'
        '-DGGML_AVX512=OFF'
        '-DGGML_AVX512_VBMI=OFF'
        '-DGGML_AVX512_VNNI=OFF'
        '-DGGML_AVX2=ON'
        '-DGGML_FMA=ON'
        '-DCMAKE_CUDA_ARCHITECTURES=86'
    ) -join ' '

    $BuildCommand = @(
        "`"$VsDevCmd`" -arch=x64"
        "set `"TMP=$BuildTemp`""
        "set `"TEMP=$BuildTemp`""
        "set `"PATH=$NinjaDir;$MsvcBin;$SdkBin;%PATH%`""
        "set `"CC=$Compiler`""
        "set `"CXX=$Compiler`""
        "set `"CUDACXX=$($Nvcc.Source)`""
        "set `"CUDAToolkit_ROOT=$CudaRoot`""
        'set "CMAKE_GENERATOR=Ninja"'
        "set `"CMAKE_BUILD_PARALLEL_LEVEL=$Jobs`""
        "set `"CMAKE_ARGS=$CmakeArgs`""
        'set "FORCE_CMAKE=1"'
        "`"$Python`" -m pip wheel --no-cache-dir --no-deps --no-binary=llama-cpp-python --wheel-dir `"$WheelDirectory`" llama-cpp-python==$LlamaVersion"
    ) -join ' && '

    Write-Output "Building llama-cpp-python $LlamaVersion for CUDA SM86 and AVX2 ($Jobs jobs)..."
    & cmd.exe /d /s /c $BuildCommand
    if ($LASTEXITCODE -ne 0) { throw 'Custom llama-cpp-python wheel build failed.' }

    $Wheel = Get-ChildItem -Path $WheelDirectory -Filter $WheelPattern -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

if (-not $Wheel) { throw 'The custom llama-cpp-python wheel was not produced.' }

& $Python -m pip install -r (Join-Path $ProjectRoot 'requirements-models.txt')
if ($LASTEXITCODE -ne 0) { throw 'Model runtime dependency installation failed.' }
& $Python -m pip install --force-reinstall --no-deps $Wheel.FullName
if ($LASTEXITCODE -ne 0) { throw 'Custom llama-cpp-python wheel installation failed.' }

Get-FileHash -Algorithm SHA256 -LiteralPath $Wheel.FullName
& $Python (Join-Path $PSScriptRoot 'verify_llama_runtime.py')
if ($LASTEXITCODE -ne 0) { throw 'The installed llama.cpp runtime is not compatible with this workstation.' }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'The model runtime has broken Python dependencies.' }
