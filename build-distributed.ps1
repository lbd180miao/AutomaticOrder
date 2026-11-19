param(
    [switch]$AgvOnly,
    [string]$Python = "$PSScriptRoot\.venv\Scripts\python.exe",
    [string]$Output = (Join-Path $PSScriptRoot ('delivery\dual-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
$logDirectory = Join-Path $PSScriptRoot 'build\package-logs'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Start-Transcript -Path (Join-Path $logDirectory ('package-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')) | Out-Null
$previousRvc = $env:RVC_CAMERA_AUTO_START
$previousDm = $env:DM_CAMERA_AUTO_CONNECT
$previousOutput = $env:DISTRIBUTED_OUTPUT
$previousData = $env:AUTOMATIC_ORDER_DATA_DIR
$previousDatabase = $env:DJANGO_DATABASE_PATH
$previousPlc = $env:PLC_LISTENER_AUTO_START
$previousFoam = $env:FOAM_STREAM_AUTO_START
$numericalThreads = @{}
foreach ($key in @('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')) {
    $numericalThreads[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, '1', 'Process')
}
try {
    if (Test-Path -LiteralPath $Output) { throw 'Use a new output directory to avoid stale deployment data.' }
    $env:RVC_CAMERA_AUTO_START = 'false'
    $env:DM_CAMERA_AUTO_CONNECT = 'false'
    $env:PLC_LISTENER_AUTO_START = 'false'
    $env:FOAM_STREAM_AUTO_START = 'false'
    & $Python tools/prepare_distributed.py
    if ($LASTEXITCODE -ne 0) { throw 'Preparation failed' }
    $env:AUTOMATIC_ORDER_DATA_DIR = Join-Path $PSScriptRoot 'build\distributed_seed'
    $env:DJANGO_DATABASE_PATH = Join-Path $env:AUTOMATIC_ORDER_DATA_DIR 'db.sqlite3'
    & $Python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Snapshot migration failed' }
    & $Python tools/clean_deployment_seed.py
    if ($LASTEXITCODE -ne 0) { throw 'Snapshot visual history cleanup failed' }
    & $Python manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Static asset collection failed' }
    & $Python -m PyInstaller --noconfirm --distpath $Output --workpath build/agv AGVControl.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed' }
    $env:DISTRIBUTED_OUTPUT = $Output
    if ($AgvOnly) {
        & $Python tools/finalize_distributed.py --agv-only
    } else {
        & $Python tools/finalize_distributed.py
    }
    if ($LASTEXITCODE -ne 0) { throw 'Release finalization failed' }
    if ($AgvOnly) {
        & $Python tools/audit_clean_release.py $Output --agv-only
    } else {
        & $Python tools/audit_clean_release.py $Output
    }
    if ($LASTEXITCODE -ne 0) { throw 'Release audit failed' }
    if (-not $AgvOnly) {
        & $Python tools/verify_release_current.py $Output
        if ($LASTEXITCODE -ne 0) { throw 'Packaged runtime verification failed' }
        & $Python tools/smoke_release_pages.py $Output
        if ($LASTEXITCODE -ne 0) { throw 'Packaged page startup verification failed' }
    }
    Write-Host "BUILD SUCCESS: $Output" -ForegroundColor Green
} finally {
    foreach ($key in $numericalThreads.Keys) {
        [Environment]::SetEnvironmentVariable($key, $numericalThreads[$key], 'Process')
    }
    $env:RVC_CAMERA_AUTO_START = $previousRvc
    $env:DM_CAMERA_AUTO_CONNECT = $previousDm
    $env:DISTRIBUTED_OUTPUT = $previousOutput
    $env:AUTOMATIC_ORDER_DATA_DIR = $previousData
    $env:DJANGO_DATABASE_PATH = $previousDatabase
    $env:PLC_LISTENER_AUTO_START = $previousPlc
    $env:FOAM_STREAM_AUTO_START = $previousFoam
    Stop-Transcript | Out-Null
    Pop-Location
}
