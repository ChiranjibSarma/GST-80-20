<#
    Invoked by deploy.bat. Reuses the Windows installer in local SQLite mode,
    then serves the portal in this console and opens the browser when healthy.
    Does not register a service, alter the firewall, or replace an existing .env.
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080
)

$ErrorActionPreference = 'Stop'
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $appDir 'install.ps1'
$server = Join-Path $appDir '.venv\Scripts\uvicorn.exe'
$url = "http://127.0.0.1:$Port"
Set-Location $appDir

function Test-PythonAvailable {
    foreach ($command in @('py', 'python', 'python3')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { continue }
        try {
            $check = if ($command -eq 'py') {
                & $command -3 -c 'import sys;print(sys.version_info >= (3, 11))' 2>$null
            } else {
                & $command -c 'import sys;print(sys.version_info >= (3, 11))' 2>$null
            }
            if ($check -eq 'True') { return $true }
        } catch { }
    }
    return $false
}

if (-not (Test-Path $installer)) {
    Write-Error "Missing install.ps1 in $appDir"
    exit 1
}

# Do not mistake another already-running local service for this launch.
$socket = New-Object System.Net.Sockets.TcpClient
$portInUse = $false
$serverExit = 1
try {
    $socket.Connect('127.0.0.1', $Port)
    $portInUse = $true
} catch {
    # A failed connection means nothing is listening on this local port.
} finally {
    $socket.Dispose()
}
if ($portInUse) {
    Write-Error "Port $Port is already in use. Try deploy.bat 8081 or stop the other service."
    exit 1
}

if (-not (Test-PythonAvailable)) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Error "Python 3.11+ is missing and winget is unavailable. Install Python from https://www.python.org/downloads/windows/ (select Add Python to PATH), then rerun deploy.bat."
        exit 1
    }
    Write-Host 'Python 3.11+ was not found. Installing Python 3.12 for this user with Windows Package Manager...'
    & $winget.Source install --id Python.Python.3.12 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Windows Package Manager could not install Python. Install it from https://www.python.org/downloads/windows/ (select Add Python to PATH), then rerun deploy.bat."
        exit 1
    }
    foreach ($pythonDir in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312'),
        (Join-Path $env:ProgramFiles 'Python312')
    )) {
        if (Test-Path (Join-Path $pythonDir 'python.exe')) {
            $env:PATH = "$pythonDir;$env:PATH"
        }
    }
    if (-not (Test-PythonAvailable)) {
        Write-Error 'Python was installed but is not visible yet. Close this window and run deploy.bat again.'
        exit 1
    }
}

Write-Host "Setting up the portal (Python 3.11+ and internet, or wheelhouse/, required)..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -NoService -Sqlite -Port $Port
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path $server)) {
    Write-Error "The installer did not create $server"
    exit 1
}

# A mirrored Drive folder transports a *closed* database between operators.
# Never point DATABASE_URL itself at that folder. The handoff cannot detect a
# remote PC whose Drive client has not synced yet; operators must coordinate.
$python = Join-Path $appDir '.venv\Scripts\python.exe'
$configuredBackupDir = (& $python -c 'from app.config import BACKUP_DIR, BACKUP_DIR_EXPLICIT; print(BACKUP_DIR if BACKUP_DIR_EXPLICIT else "")').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not read the backup folder configuration.' }
if (-not $configuredBackupDir) {
    Write-Host ''
    Write-Host 'For one-at-a-time handoff, enter an existing Google Drive MIRRORED folder.' -ForegroundColor Yellow
    Write-Host 'Leave blank to run only on this PC without shared handoff.' -ForegroundColor Yellow
    $configuredBackupDir = (Read-Host 'Mirrored Drive folder').Trim()
    if ($configuredBackupDir) {
        if (-not (Test-Path -LiteralPath $configuredBackupDir -PathType Container)) {
            Write-Error "Folder does not exist: $configuredBackupDir"
            exit 1
        }
        $configuredBackupDir = (Resolve-Path -LiteralPath $configuredBackupDir).Path
        $safePath = $configuredBackupDir.Replace('\', '/')
        Add-Content -Path (Join-Path $appDir '.env') -Value "BACKUP_DIR=`"$safePath`""
        $env:BACKUP_DIR = $configuredBackupDir
    }
}

$useHandoff = [bool]$configuredBackupDir
if ($useHandoff) {
    if (-not (Test-Path -LiteralPath $configuredBackupDir -PathType Container)) {
        Write-Error "The configured Drive folder is unavailable: $configuredBackupDir. Wait for Drive to sync."
        exit 1
    }
    Write-Host ''
    Write-Host 'Confirm Google Drive reports Up to date and no other person has the portal open.' -ForegroundColor Yellow
    $ready = Read-Host 'Type YES to continue'
    if ($ready -cne 'YES') { Write-Error 'Database handoff cancelled.'; exit 1 }
    $currentDb = Join-Path $configuredBackupDir 'gst8020-current.sqlite3'
    if (Test-Path -LiteralPath $currentDb) {
        $handoffState = Join-Path $appDir 'var\handoff-state.json'
        if (Test-Path -LiteralPath $handoffState) {
            & $python -m app.handoff pull
        } else {
            Write-Host 'First load on this PC: its current local database will be preserved before replacement.' -ForegroundColor Yellow
            Write-Host 'After loading, use the administrator credentials from the shared database.' -ForegroundColor Yellow
            $adopt = Read-Host 'Type ADOPT to load the shared database'
            if ($adopt -cne 'ADOPT') { Write-Error 'First load cancelled.'; exit 1 }
            & $python -m app.handoff pull --adopt
        }
    } else {
        Write-Host 'No current database appears in this Drive folder.' -ForegroundColor Yellow
        Write-Host 'Only the FIRST operator may initialize it; do not do this if another PC has a copy still syncing.' -ForegroundColor Yellow
        $initialize = Read-Host 'Type FIRST to initialize from this PC'
        if ($initialize -cne 'FIRST') { Write-Error 'Initialization cancelled.'; exit 1 }
        & $python -m app.handoff publish --initialize
    }
    if ($LASTEXITCODE -ne 0) { Write-Error 'Database handoff failed. The portal was not opened.'; exit 1 }
}

Write-Host ""
Write-Host "Opening $url when the portal is ready. Keep this window open; Ctrl+C stops it."
$browserJob = Start-Job -ScriptBlock {
    param($address)
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $response = Invoke-WebRequest "$address/healthz" -UseBasicParsing -TimeoutSec 1
            if ($response.Content.Trim() -eq 'ok') {
                Start-Process $address
                return
            }
        } catch { }
    }
} -ArgumentList $url

try {
    & $server app.main:app --host 127.0.0.1 --port $Port
    $serverExit = $LASTEXITCODE
} finally {
    Stop-Job $browserJob -ErrorAction SilentlyContinue
    Remove-Job $browserJob -Force -ErrorAction SilentlyContinue
    if ($useHandoff) {
        Write-Host ''
        Write-Host 'Publishing a consistent current database for the next operator...'
        & $python -m app.handoff publish
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'HANDOFF FAILED. Do not let another PC start until this local database is recovered or reconciled.' -ForegroundColor Red
            $serverExit = 1
        }
    }
}
exit $serverExit
