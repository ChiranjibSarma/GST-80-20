<#
    Invoked by deploy.bat. Reuses the Windows installer in local SQLite mode,
    then serves the portal in this console and opens the browser when healthy.
    Does not register a service, alter the firewall, or replace an existing .env.
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,
    [switch]$PrepareOnly
)

$ErrorActionPreference = 'Stop'
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $appDir 'install.ps1'
$server = Join-Path $appDir '.venv\Scripts\uvicorn.exe'
Set-Location $appDir

# Reject an inherited server/PostgreSQL configuration BEFORE installing Python
# or packages. This BAT is a local SQLite deployment, not a database migration.
$existingEnv = Join-Path $appDir '.env'
if (Test-Path -LiteralPath $existingEnv) {
    $dbLine = Select-String -LiteralPath $existingEnv -Pattern '^\s*DATABASE_URL\s*=\s*(.*)$' | Select-Object -Last 1
    if ($dbLine) {
        $configuredUrl = $dbLine.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
        if ($configuredUrl -and $configuredUrl -notmatch '^sqlite:') {
            Write-Error 'This folder is configured for PostgreSQL in .env. Local deploy.bat will not alter that database or silently create a new SQLite database. Migrate explicitly or use a clean EXE installation.'
            exit 1
        }
    }
}
if ($env:DATABASE_URL -and $env:DATABASE_URL -notmatch '^sqlite:') {
    Write-Error 'DATABASE_URL in this PowerShell environment points to PostgreSQL/non-SQLite. Clear it before local deployment; no database was changed.'
    exit 1
}

# Some client machines leave Windows long-path support disabled. Pip's nested
# wheel metadata can then hit WinError 206 in a deeply extracted OneDrive ZIP.
$projectedWheelPath = Join-Path $appDir '.venv\Lib\site-packages\httptools-0.8.0.dist-info\licenses\vendor\http-parser'
if ($projectedWheelPath.Length -ge 240) {
    Write-Error "This application path is too deep for reliable Windows package installation ($($projectedWheelPath.Length) characters). Extract a clean source ZIP under a short local folder such as C:\GST-80-20, or use install_from_zip.bat to install under LocalAppData. Preserve any existing var\finops.db, licence and .env before relocating an existing installation."
    exit 1
}

# Keep one launcher/recovery session per checkout. This lock is released by
# Windows when the console process exits, including interrupted launches.
$hashProvider = [System.Security.Cryptography.SHA256]::Create()
try {
    $pathHash = [BitConverter]::ToString($hashProvider.ComputeHash(
        [System.Text.Encoding]::UTF8.GetBytes($appDir.ToLowerInvariant()))).Replace('-', '')
} finally { $hashProvider.Dispose() }
$launchMutex = [System.Threading.Mutex]::new($false, "Local\GST8020-$pathHash")
try { $ownsLaunchMutex = $launchMutex.WaitOne(0) }
catch [System.Threading.AbandonedMutexException] { $ownsLaunchMutex = $true }
if (-not $ownsLaunchMutex) {
    Write-Error 'This installation is already being launched or is running. Use its existing browser window; do not run another launcher during recovery.'
    exit 1
}

function Test-PythonAvailable {
    if ($env:GST8020_PYTHON) {
        $requestedPython = $env:GST8020_PYTHON.Trim('"')
        if (-not (Test-Path -LiteralPath $requestedPython -PathType Leaf)) {
            Write-Error "GST8020_PYTHON points to a missing file: $requestedPython"
            exit 1
        }
        try {
            $check = & $requestedPython -c 'import sys;print((3,11)<=sys.version_info<(3,14) and sys.maxsize>2**32)' 2>$null
            if ($check -eq 'True') { return $true }
        } catch { }
        Write-Error 'GST8020_PYTHON must point to working Python 3.11-3.13 (64-bit). No other Python was tried.'
        exit 1
    }
    foreach ($candidate in @('py -3.12', 'py -3.13', 'py -3.11', 'py -3', 'python', 'python3')) {
        $command, $argument = $candidate -split ' ', 2
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { continue }
        try {
            $check = if ($argument) {
                & $command $argument -c 'import sys;print((3,11)<=sys.version_info<(3,14) and sys.maxsize>2**32)' 2>$null
            } else {
                & $command -c 'import sys;print((3,11)<=sys.version_info<(3,14) and sys.maxsize>2**32)' 2>$null
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

# Probe by binding, not connecting: an occupied/reserved port may not answer
# a connection, but Uvicorn still could not bind to it.
$requestedPort = $Port
while ($Port -le 65535) {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    $probe.ExclusiveAddressUse = $true
    try {
        $probe.Start()
        break
    } catch [System.Net.Sockets.SocketException] {
        $Port++
    } finally {
        $probe.Stop()
    }
}
if ($Port -gt 65535) {
    Write-Error "No available local TCP port was found from $requestedPort through 65535."
    exit 1
}
if ($Port -ne $requestedPort) {
    Write-Host "Port $requestedPort is unavailable; using port $Port instead." -ForegroundColor Yellow
}
$url = "http://127.0.0.1:$Port"
$serverExit = 1

if (-not (Test-PythonAvailable)) {
    if ($env:GST8020_NO_AUTO_INSTALL -eq '1') {
        Write-Error 'Supported Python 3.11-3.13 is missing. Automatic installation is disabled. Install Python 3.12 from the official installer, then rerun deploy.bat.'
        exit 1
    }
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Error "Supported Python (3.11-3.13) is missing and winget is unavailable. Install Python 3.12 with Add Python to PATH, then rerun deploy.bat. Python 3.14 is not validated for this package."
        exit 1
    }
    Write-Host 'Supported Python (3.11-3.13) was not found. Installing Python 3.12 for this user with Windows Package Manager...'
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

# Backups may go to a client-controlled Google Drive mirror, but the live
# database is local and never loaded from or published to that folder.
$python = Join-Path $appDir '.venv\Scripts\python.exe'
$backupOutput = & $python -m app.deploy_check backup-dir
if ($LASTEXITCODE -ne 0) { Write-Error 'Could not read the backup folder configuration.'; exit 1 }
$configuredBackupDir = [string]($backupOutput | Select-Object -First 1)
$configuredBackupDir = $configuredBackupDir.Trim()
if (-not $configuredBackupDir) {
    Write-Host ''
    Write-Host 'Optional: enter an existing Google Drive MIRRORED folder for dated backups.' -ForegroundColor Yellow
    Write-Host 'Leave blank to keep backups in local var\backups.' -ForegroundColor Yellow
    $configuredBackupDir = (Read-Host 'Backup folder').Trim()
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
if ($configuredBackupDir -and -not (Test-Path -LiteralPath $configuredBackupDir -PathType Container)) {
    Write-Warning "Configured backup folder is unavailable: $configuredBackupDir. Calculations can run, but their backups will fail until the folder returns."
}
$liveDatabase = & $python -m app.deploy_check local-db
if ($LASTEXITCODE -ne 0) { Write-Error 'The configured database is not a safe local SQLite file. Review DATABASE_URL in .env.'; exit 1 }
Write-Host "Live database: $liveDatabase"
if ([string]$liveDatabase -match '(?i)[\\/](?:OneDrive[^\\/]*|Google Drive|Dropbox)[\\/]') {
    Write-Warning 'The live database is inside a synced folder. For client deployment, copy the app to a non-synced local folder before use; configure Drive only as the backup destination.'
}

& $python -m app.recovery
if ($LASTEXITCODE -ne 0) { Write-Error 'Database recovery did not complete. No portal was started.'; exit 1 }

if ($PrepareOnly) {
    $installationId = (Get-Content -LiteralPath (Join-Path $appDir 'var\installation-id') -Raw).Trim()
    Write-Host ''
    Write-Host 'Installation prepared. It has not been started.' -ForegroundColor Green
    Write-Host "Installation ID: $installationId" -ForegroundColor White
    exit 0
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
}
exit $serverExit
