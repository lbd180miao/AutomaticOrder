param([string]$Python = "$PSScriptRoot\.venv\Scripts\python.exe")
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
$previousRvc = $env:RVC_CAMERA_AUTO_START
$previousDm = $env:DM_CAMERA_AUTO_CONNECT
try {
    $env:RVC_CAMERA_AUTO_START = 'false'
    $env:DM_CAMERA_AUTO_CONNECT = 'false'
    & $Python -c "import PyInstaller, waitress, django, PyRVC, open3d"
    if ($LASTEXITCODE -ne 0) { throw 'Missing build/runtime dependencies. See docs/packaging.md.' }
    & $Python manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw 'collectstatic failed' }
    & $Python -m PyInstaller --noconfirm --clean MyApp.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    Write-Host 'Built dist\MyApp. Deploy database, media and camera SDKs as documented in docs/packaging.md.'
} finally {
    $env:RVC_CAMERA_AUTO_START = $previousRvc
    $env:DM_CAMERA_AUTO_CONNECT = $previousDm
    Pop-Location
}
