[CmdletBinding()]
param([string]$Python = '', [switch]$InstallBuildDependencies)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$env:PYINSTALLER_CONFIG_DIR = Join-Path $repo '.tmp\pyinstaller-cache'
$buildWork = Join-Path $repo ('.tmp\pyinstaller-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
if (-not $Python) { $Python = Join-Path $repo '.venv\Scripts\python.exe' }
if ($InstallBuildDependencies) {
    & $Python -m pip install -r requirements.txt pyinstaller==6.22.0
    if ($LASTEXITCODE) { throw 'Build dependencies did not install.' }
}
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --noupx `
    --name GST-80-20-Setup --distpath distribution\windows --workpath $buildWork `
    --specpath .tmp --paths $repo `
    --add-data "$repo\app\templates;app\templates" --add-data "$repo\app\static;app\static" `
    --add-data "$repo\app\license_public_key.pem;app" `
    --hidden-import sqlalchemy.dialects.sqlite --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops.asyncio --hidden-import uvicorn.protocols.http.h11_impl `
    --hidden-import uvicorn.lifespan.on packaging\windows_launcher.py
if ($LASTEXITCODE) { throw 'EXE build failed.' }
Copy-Item -LiteralPath packaging\test_no_python.ps1 -Destination distribution\windows\test_no_python.ps1
Get-FileHash distribution\windows\GST-80-20-Setup.exe -Algorithm SHA256
